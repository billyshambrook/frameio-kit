"""Installation routes for app installation flow.

This module provides endpoints for the installation flow including
landing page, workspace selection, and installation processing.
OAuth is handled by the auth routes module.
"""

import logging
import re
import secrets
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ._install_manager import InstallationManager
from ._install_ui import (
    render_install_page,
    render_manage_page,
    render_workspace_selection,
)
from ._oauth import AdobeOAuthClient, TokenManager, get_oauth_redirect_url, infer_oauth_url

logger = logging.getLogger(__name__)

# Constants for session configuration
OAUTH_STATE_TTL = 600  # 10 minutes
INSTALL_SESSION_TTL = 600  # 10 minutes

# UUID v4 pattern for workspace ID validation
WORKSPACE_ID_PATTERN = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$", re.IGNORECASE
)


async def _install_landing_page(request: Request) -> HTMLResponse:
    """Render the installation landing page.

    Returns:
        HTML page describing what will be installed.
    """
    # Get installation manager from app state
    install_manager: InstallationManager = request.app.state.install_manager
    base_url: str = infer_oauth_url(request, "")

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
    # Include IP and timestamp for additional security
    from datetime import datetime

    state_data: dict[str, Any] = {
        "flow": "installation",  # Distinguish from regular auth flow
        "timestamp": datetime.now().isoformat(),
        "ip": request.client.host if request.client else None,
    }
    state_key = f"oauth_state:{state}"
    await token_manager.storage.put(state_key, state_data, ttl=OAUTH_STATE_TTL)

    # Redirect to Adobe OAuth
    auth_url = oauth_client.get_authorization_url(
        state, get_oauth_redirect_url(request.app.state.oauth_config, request)
    )
    return RedirectResponse(auth_url)


async def _install_workspace_selection(request: Request) -> HTMLResponse:
    """Display workspace selection page.

    Query parameters:
        session: Installation session ID from OAuth callback.

    Returns:
        HTML page with workspace checkboxes and installation status.
    """
    session_id = request.query_params.get("session")
    if not session_id:
        return HTMLResponse("<h1>Error</h1><p>Missing session parameter</p>", status_code=400)

    # Get session data
    token_manager: TokenManager = request.app.state.token_manager
    install_manager: InstallationManager = request.app.state.install_manager
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
                # Check if already installed
                installation = await install_manager.get_installation(ws.id)
                current_version = install_manager.manifest.compute_hash()

                status = "not_installed"
                if installation and installation.status == "active":
                    if installation.manifest_version == current_version:
                        status = "installed"
                    else:
                        status = "update_available"

                workspaces.append(
                    {
                        "id": ws.id,
                        "name": ws.name,
                        "status": status,
                    }
                )

    finally:
        await client.close()

    # Update session with workspace data for later
    session_data["session_id"] = session_id  # Store for form submission
    await token_manager.storage.put(session_key, session_data, ttl=INSTALL_SESSION_TTL)

    # Render selection page
    base_url: str = infer_oauth_url(request, "")
    html = render_workspace_selection(workspaces, base_url, session_id)
    return HTMLResponse(html)


async def _install_process(request: Request) -> HTMLResponse:
    """Process installation/uninstallation to selected workspaces.

    This handles both installing to new workspaces and uninstalling from
    workspaces that were previously installed but are now unchecked.

    Form data:
        workspace_ids: List of workspace IDs to install to.
        all_workspace_ids: Hidden field with all available workspace IDs.

    Query parameters:
        session: Installation session ID.

    Returns:
        HTML page with installation/uninstallation results.
    """
    session_id = request.query_params.get("session")
    if not session_id:
        return HTMLResponse("<h1>Error</h1><p>Missing session parameter</p>", status_code=400)

    # Get session data
    token_manager: TokenManager = request.app.state.token_manager
    install_manager: InstallationManager = request.app.state.install_manager
    session_key = f"install_session:{session_id}"
    session_data = await token_manager.storage.get(session_key)

    if not session_data:
        return HTMLResponse("<h1>Error</h1><p>Invalid or expired session</p>", status_code=400)

    user_id = session_data["user_id"]
    access_token = session_data["access_token"]

    # Parse form data
    form_data = await request.form()
    selected_workspace_ids = set(form_data.getlist("workspace_ids"))
    all_workspace_ids = form_data.get("all_workspace_ids", "").split(",")
    all_workspace_ids = [ws_id.strip() for ws_id in all_workspace_ids if ws_id.strip()]

    # Validate workspace ID format (UUID v4)
    for ws_id in list(selected_workspace_ids) + all_workspace_ids:
        if not WORKSPACE_ID_PATTERN.match(ws_id):
            logger.warning("Invalid workspace ID format received: %s", ws_id)
            return HTMLResponse(
                f"<h1>Error</h1><p>Invalid workspace ID format: {ws_id}</p>",
                status_code=400,
            )

    # Get current installations to determine what to uninstall
    current_installations = await install_manager.list_installations(user_id)
    currently_installed_ids = {inst.workspace_id for inst in current_installations}

    # Determine which workspaces to install and uninstall
    to_install = [ws_id for ws_id in selected_workspace_ids if ws_id in all_workspace_ids]
    to_uninstall = [
        ws_id for ws_id in currently_installed_ids if ws_id in all_workspace_ids and ws_id not in selected_workspace_ids
    ]

    # Combined results
    install_results = {}
    install_errors = {}
    uninstall_results = {}
    uninstall_errors = {}

    # Perform installations
    if to_install:
        install_result = await install_manager.install(
            user_id=user_id,
            user_token=access_token,
            workspace_ids=to_install,
            base_url=infer_oauth_url(request, ""),
        )
        install_results = install_result.workspace_results
        install_errors = install_result.errors

    # Perform uninstallations
    if to_uninstall:
        uninstall_result = await install_manager.uninstall(
            user_id=user_id,
            user_token=access_token,
            workspace_ids=to_uninstall,
            base_url=infer_oauth_url(request, ""),
        )
        uninstall_results = uninstall_result.workspace_results
        uninstall_errors = uninstall_result.errors

    # Clean up session
    await token_manager.storage.delete(session_key)

    # Render results
    from ._install_ui import render_process_results_page

    html = render_process_results_page(
        install_results=install_results,
        install_errors=install_errors,
        uninstall_results=uninstall_results,
        uninstall_errors=uninstall_errors,
    )
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

    # Render manage page with user_id
    base_url: str = infer_oauth_url(request, "")
    html = render_manage_page(installations, base_url, user_id)
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
    base_url: str = infer_oauth_url(request, "/install/manage")
    if result.success:
        return RedirectResponse(f"{base_url}?user_id={user_id}")
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
        - GET /install/oauth/login - OAuth initiation (redirects to /auth/callback)
        - GET /install/workspaces - Workspace selection
        - POST /install/process - Process installation
        - GET /install/manage - Manage installations
        - POST /install/uninstall - Uninstall

        OAuth callback is handled by /auth/callback (in _auth_routes.py)
    """
    return [
        Route("/install", _install_landing_page, methods=["GET"]),
        Route("/install/oauth/login", _install_oauth_login, methods=["GET"]),
        Route("/install/workspaces", _install_workspace_selection, methods=["GET"]),
        Route("/install/process", _install_process, methods=["POST"]),
        Route("/install/manage", _install_manage, methods=["GET"]),
        Route("/install/uninstall", _install_uninstall, methods=["POST"]),
    ]
