"""OAuth and installation routes for app installation flow.

This module provides endpoints for the installation flow including
landing page, OAuth, workspace selection, and installation processing.
"""

import secrets
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ._install_manager import InstallationManager
from ._install_ui import (
    render_install_page,
    render_manage_page,
    render_success_page,
    render_workspace_selection,
)
from ._oauth import AdobeOAuthClient, TokenManager


async def _install_landing_page(request: Request) -> HTMLResponse:
    """Render the installation landing page.

    Returns:
        HTML page describing what will be installed.
    """
    # Get installation manager from app state
    install_manager: InstallationManager = request.app.state.install_manager
    base_url: str = request.app.state.install_base_url

    html = render_install_page(install_manager.manifest, base_url)
    return HTMLResponse(html)


async def _install_oauth_login(request: Request) -> RedirectResponse | HTMLResponse:
    """Initiate OAuth flow for installation.

    Returns:
        Redirect to Adobe IMS authorization page.
    """
    # Get OAuth client and token manager from app state
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client
    token_manager: TokenManager = request.app.state.token_manager

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)

    # Store state in storage backend with 10-minute TTL (600 seconds)
    state_data: dict[str, Any] = {
        "flow": "installation",  # Distinguish from regular auth flow
    }
    state_key = f"oauth_state:{state}"
    await token_manager.storage.put(state_key, state_data, ttl=600)

    # Redirect to Adobe OAuth
    auth_url = oauth_client.get_authorization_url(state)
    return RedirectResponse(auth_url)


async def _install_oauth_callback(request: Request) -> HTMLResponse | RedirectResponse:
    """Handle OAuth callback for installation flow.

    Query parameters:
        code: Authorization code (present on success)
        state: CSRF state token (required)
        error: Error code (present on failure)

    Returns:
        Redirect to workspace selection or error page.
    """
    # Get dependencies from app state
    token_manager: TokenManager = request.app.state.token_manager
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client
    base_url: str = request.app.state.install_base_url

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    # Check for OAuth error
    if error:
        error_description = request.query_params.get("error_description", "Unknown error")
        return HTMLResponse(
            f"""
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>❌ Authentication Failed</h1>
                <p><strong>Error:</strong> {error}</p>
                <p><strong>Description:</strong> {error_description}</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Validate required parameters
    if not code or not state:
        return HTMLResponse(
            "<h1>Error</h1><p>Missing code or state parameter</p>",
            status_code=400,
        )

    # Verify and retrieve state data from storage (CSRF protection)
    state_key = f"oauth_state:{state}"
    state_data: dict[str, Any] | None = await token_manager.storage.get(state_key)

    if not state_data or state_data.get("flow") != "installation":
        return HTMLResponse(
            """
            <html>
            <head><title>Invalid State</title></head>
            <body>
                <h1>❌ Invalid or Expired State</h1>
                <p>The authentication state token is invalid or has expired.</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Delete state after retrieval (consume once)
    await token_manager.storage.delete(state_key)

    try:
        # Exchange code for tokens
        token_data = await oauth_client.exchange_code(code)

        # Get user ID from token (we need to make an API call to get this)
        from ._client import Client

        temp_client = Client(token=token_data.access_token)
        try:
            user = await temp_client.users.me()
            user_id = user.data.id
        finally:
            await temp_client.close()

        # Store token temporarily for installation process
        # Use a temporary key since we don't have the user_id yet
        install_session_id = secrets.token_urlsafe(32)
        session_key = f"install_session:{install_session_id}"
        await token_manager.storage.put(
            session_key,
            {
                "user_id": user_id,
                "access_token": token_data.access_token,
            },
            ttl=600,  # 10 minutes
        )

        # Redirect to workspace selection with session ID
        return RedirectResponse(f"{base_url}/install/workspaces?session={install_session_id}")

    except Exception as e:
        return HTMLResponse(
            f"""
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>❌ Authentication Failed</h1>
                <p><strong>Error:</strong> {str(e)}</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=500,
        )


async def _install_workspace_selection(request: Request) -> HTMLResponse:
    """Display workspace selection page.

    Query parameters:
        session: Installation session ID from OAuth callback.

    Returns:
        HTML page with workspace checkboxes.
    """
    session_id = request.query_params.get("session")
    if not session_id:
        return HTMLResponse("<h1>Error</h1><p>Missing session parameter</p>", status_code=400)

    # Get session data
    token_manager: TokenManager = request.app.state.token_manager
    session_key = f"install_session:{session_id}"
    session_data = await token_manager.storage.get(session_key)

    if not session_data:
        return HTMLResponse("<h1>Error</h1><p>Invalid or expired session</p>", status_code=400)

    user_id = session_data["user_id"]
    access_token = session_data["access_token"]

    # Fetch user's workspaces
    from ._client import Client

    client = Client(token=access_token)
    try:
        # Get all accounts
        accounts = await client.accounts.index()

        # Get workspaces for each account
        workspaces = []
        for account in accounts.data:
            ws_list = await client.workspaces.index(account_id=account.id)
            for ws in ws_list.data:
                workspaces.append({"id": ws.id, "name": ws.name})

    finally:
        await client.close()

    # Update session with workspace data for later
    session_data["session_id"] = session_id  # Store for form submission
    await token_manager.storage.put(session_key, session_data, ttl=600)

    # Render selection page
    base_url: str = request.app.state.install_base_url
    html = render_workspace_selection(workspaces, f"{base_url}?session={session_id}")
    return HTMLResponse(html)


async def _install_process(request: Request) -> HTMLResponse:
    """Process installation to selected workspaces.

    Form data:
        workspace_ids: List of workspace IDs to install to.

    Query parameters:
        session: Installation session ID.

    Returns:
        HTML page with installation results.
    """
    session_id = request.query_params.get("session")
    if not session_id:
        return HTMLResponse("<h1>Error</h1><p>Missing session parameter</p>", status_code=400)

    # Get session data
    token_manager: TokenManager = request.app.state.token_manager
    session_key = f"install_session:{session_id}"
    session_data = await token_manager.storage.get(session_key)

    if not session_data:
        return HTMLResponse("<h1>Error</h1><p>Invalid or expired session</p>", status_code=400)

    user_id = session_data["user_id"]
    access_token = session_data["access_token"]

    # Parse form data
    form_data = await request.form()
    workspace_ids = form_data.getlist("workspace_ids")

    if not workspace_ids:
        return HTMLResponse("<h1>Error</h1><p>No workspaces selected</p>", status_code=400)

    # Perform installation
    install_manager: InstallationManager = request.app.state.install_manager

    result = await install_manager.install(
        user_id=user_id,
        user_token=access_token,
        workspace_ids=workspace_ids,
    )

    # Clean up session
    await token_manager.storage.delete(session_key)

    # Render results
    html = render_success_page(result.workspace_results, result.errors)
    return HTMLResponse(html)


async def _install_manage(request: Request) -> HTMLResponse:
    """Display manage installations page.

    Requires user to be authenticated via regular OAuth.

    Query parameters:
        user_id: Frame.io user ID (from auth flow).

    Returns:
        HTML page with list of installations.
    """
    user_id = request.query_params.get("user_id")
    if not user_id:
        return HTMLResponse("<h1>Error</h1><p>Missing user_id parameter</p>", status_code=400)

    # Get installations
    install_manager: InstallationManager = request.app.state.install_manager
    installations = await install_manager.list_installations(user_id)

    # Render manage page
    base_url: str = request.app.state.install_base_url
    html = render_manage_page(installations, base_url)
    return HTMLResponse(html)


async def _install_uninstall(request: Request) -> Response:
    """Uninstall app from a workspace.

    Form data:
        workspace_id: Workspace ID to uninstall from.
        user_id: User performing the uninstall.

    Returns:
        Redirect to manage page or error.
    """
    form_data = await request.form()
    workspace_id = form_data.get("workspace_id")
    user_id = form_data.get("user_id")

    if not workspace_id or not user_id:
        return HTMLResponse("<h1>Error</h1><p>Missing required parameters</p>", status_code=400)

    # Get user's token
    token_manager: TokenManager = request.app.state.token_manager
    token_data = await token_manager.get_token(user_id)

    if not token_data:
        return HTMLResponse("<h1>Error</h1><p>User not authenticated</p>", status_code=401)

    # Perform uninstall
    install_manager: InstallationManager = request.app.state.install_manager

    result = await install_manager.uninstall(
        user_id=user_id,
        user_token=token_data.access_token,
        workspace_ids=[workspace_id],
    )

    # Redirect back to manage page
    base_url: str = request.app.state.install_base_url
    if result.success:
        return RedirectResponse(f"{base_url}/install/manage?user_id={user_id}")
    else:
        error_msg = result.errors.get(workspace_id, "Unknown error")
        return HTMLResponse(f"<h1>Uninstall Failed</h1><p>{error_msg}</p>", status_code=500)


def create_install_routes() -> list[Route]:
    """Create installation routes.

    Returns:
        List of Starlette Route objects to mount in the app.

    Note:
        These routes will be mounted at:
        - GET /install - Landing page
        - GET /install/oauth/login - OAuth initiation
        - GET /install/oauth/callback - OAuth callback
        - GET /install/workspaces - Workspace selection
        - POST /install/process - Process installation
        - GET /install/manage - Manage installations
        - POST /install/uninstall - Uninstall
    """
    return [
        Route("/install", _install_landing_page, methods=["GET"]),
        Route("/install/oauth/login", _install_oauth_login, methods=["GET"]),
        Route("/install/oauth/callback", _install_oauth_callback, methods=["GET"]),
        Route("/install/workspaces", _install_workspace_selection, methods=["GET"]),
        Route("/install/process", _install_process, methods=["POST"]),
        Route("/install/manage", _install_manage, methods=["GET"]),
        Route("/install/uninstall", _install_uninstall, methods=["POST"]),
    ]
