"""OAuth authentication routes for Adobe IMS integration.

This module provides OAuth 2.0 endpoints for the authorization code flow,
including login initiation and callback handling with CSRF protection.
"""

import logging
import secrets
from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from ._oauth import AdobeOAuthClient, TokenManager, get_oauth_redirect_url, infer_oauth_url

logger = logging.getLogger(__name__)

# Constants for session configuration
OAUTH_STATE_TTL = 600  # 10 minutes
INSTALL_SESSION_TTL = 600  # 10 minutes


async def _login_endpoint(request: Request) -> RedirectResponse | HTMLResponse:
    """Initiate OAuth flow by redirecting to Adobe IMS.

    Query parameters:
        user_id: Frame.io user ID (required)
        interaction_id: Frame.io interaction ID for multi-step flows (optional)

    Returns:
        Redirect to Adobe IMS authorization page.
    """
    from ._oauth import OAuthConfig

    # Get oauth config and token manager from app state
    oauth_config: OAuthConfig = request.app.state.oauth_config
    token_manager: TokenManager = request.app.state.token_manager

    # Extract user context from query params
    user_id = request.query_params.get("user_id")
    interaction_id = request.query_params.get("interaction_id")

    if not user_id:
        return HTMLResponse(
            "<h1>Error</h1><p>Missing user_id parameter</p>",
            status_code=400,
        )

    # Get redirect URL - use explicit config or infer from request
    redirect_url = get_oauth_redirect_url(oauth_config, request)

    # Get shared OAuth client from app state
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)

    # Store state in storage backend with 10-minute TTL (600 seconds)
    # Include IP and timestamp for additional security
    state_data: dict[str, Any] = {
        "user_id": user_id,
        "interaction_id": interaction_id,
        "timestamp": datetime.now().isoformat(),
        "ip": request.client.host if request.client else None,
    }
    state_key = f"oauth_state:{state}"
    await token_manager.storage.put(state_key, state_data, ttl=OAUTH_STATE_TTL)

    # Redirect to Adobe OAuth
    auth_url = oauth_client.get_authorization_url(state, redirect_url)
    return RedirectResponse(auth_url)


async def _callback_endpoint(request: Request) -> HTMLResponse | RedirectResponse:
    """Handle OAuth callback from Adobe IMS.

    Supports both regular authentication and installation flows.

    Query parameters:
        code: Authorization code (present on success)
        state: CSRF state token (required)
        error: Error code (present on failure)

    Returns:
        HTML page with success or error message, or redirect to workspace selection for installation.
    """
    # Get token manager from app state
    token_manager: TokenManager = request.app.state.token_manager

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

    if not state_data:
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

    # Validate IP matches (protection against token fixation attacks)
    request_ip = request.client.host if request.client else None
    state_ip = state_data.get("ip")
    if state_ip and request_ip and state_ip != request_ip:
        logger.warning(
            "OAuth state token used from different IP: %s (state) vs %s (request). Possible token fixation attack.",
            state_ip,
            request_ip,
        )
        # For now, log but continue - may reject in stricter security mode
        # In production, consider rejecting based on security requirements

    # Delete state after retrieval (consume once)
    await token_manager.storage.delete(state_key)

    try:
        # Exchange code for tokens
        token_data = await request.app.state.oauth_client.exchange_code(
            code, get_oauth_redirect_url(request.app.state.oauth_config, request)
        )

        # Check if this is an installation flow
        if state_data.get("flow") == "installation":
            # Installation flow - get user ID and redirect to workspace selection
            from ._client import Client

            temp_client = Client(token=token_data.access_token)
            try:
                user = await temp_client.users.show()
                user_id = user.data.id
            finally:
                await temp_client.close()

            # Store token temporarily for installation process
            import secrets

            install_session_id = secrets.token_urlsafe(32)
            session_key = f"install_session:{install_session_id}"
            await token_manager.storage.put(
                session_key,
                {
                    "user_id": user_id,
                    "access_token": token_data.access_token,
                },
                ttl=INSTALL_SESSION_TTL,
            )

            # Redirect to workspace selection
            install_base_url: str = infer_oauth_url(request, "/install/workspaces")
            return RedirectResponse(f"{install_base_url}?session={install_session_id}")

        # Regular auth flow - user_id is required
        user_id = state_data.get("user_id")
        if not user_id:
            return HTMLResponse(
                "<h1>Error</h1><p>Missing user_id in authentication state</p>",
                status_code=400,
            )

        # Store token for regular auth
        await token_manager.store_token(user_id, token_data)

        # Success page
        return HTMLResponse(
            """
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 1rem;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 { color: #2d3748; margin: 0 0 1rem; }
                    p { color: #4a5568; line-height: 1.6; }
                    .emoji { font-size: 4rem; margin-bottom: 1rem; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="emoji">✅</div>
                    <h1>Authentication Successful!</h1>
                    <p>You have successfully signed in with Adobe.</p>
                    <p>You can now close this window and return to Frame.io.</p>
                    <script>
                        setTimeout(() => window.close(), 3000);
                    </script>
                </div>
            </body>
            </html>
            """
        )
    except Exception as e:
        logger.error("OAuth callback error: %s", str(e), exc_info=True)
        # Don't expose internal error details to users
        return HTMLResponse(
            """
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>❌ Authentication Failed</h1>
                <p>An unexpected error occurred during authentication.</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=500,
        )


def create_auth_routes() -> list[Route]:
    """Create OAuth authentication routes.

    Returns:
        List of Starlette Route objects to mount in the app.

    Note:
        These routes will be mounted at:
        - GET /auth/login - Initiates OAuth flow
        - GET /auth/callback - Handles OAuth callback

        Routes expect oauth_config and token_manager to be available in app.state.

    Example:
        ```python
        from starlette.applications import Starlette

        app = Starlette()
        auth_routes = create_auth_routes()
        app.routes.extend(auth_routes)
        ```
    """
    return [
        Route("/auth/login", _login_endpoint, methods=["GET"]),
        Route("/auth/callback", _callback_endpoint, methods=["GET"]),
    ]
