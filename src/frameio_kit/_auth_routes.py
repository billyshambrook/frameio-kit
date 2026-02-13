"""OAuth authentication routes for Adobe IMS integration.

This module provides OAuth 2.0 endpoints for the authorization code flow,
including login initiation and callback handling using stateless signed tokens.
"""

import html
import logging
from typing import TypedDict

from itsdangerous import BadSignature, SignatureExpired
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from ._oauth import AdobeOAuthClient, OAuthConfig, StateSerializer, TokenManager, get_oauth_redirect_url

logger = logging.getLogger(__name__)


class OAuthStateData(TypedDict):
    """Typed dictionary for OAuth state data embedded in signed tokens.

    Attributes:
        user_id: Frame.io user ID initiating the auth flow.
        interaction_id: Optional interaction ID for multi-step flows.
        redirect_url: OAuth redirect URL to use for the callback.
    """

    user_id: str
    interaction_id: str | None
    redirect_url: str


async def _login_endpoint(request: Request) -> RedirectResponse | HTMLResponse:
    """Initiate OAuth flow by redirecting to Adobe IMS.

    Query parameters:
        user_id: Frame.io user ID (required)
        interaction_id: Frame.io interaction ID for multi-step flows (optional)

    Returns:
        Redirect to Adobe IMS authorization page.
    """
    # Get oauth config from app state
    oauth_config: OAuthConfig = request.app.state.oauth_config
    state_serializer: StateSerializer = request.app.state.state_serializer

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

    # Create signed state token with embedded data (stateless - no storage needed)
    state_data: OAuthStateData = {
        "user_id": user_id,
        "interaction_id": interaction_id,
        "redirect_url": redirect_url,
    }
    state = state_serializer.dumps(state_data)

    # Redirect to Adobe OAuth
    auth_url = oauth_client.get_authorization_url(state, redirect_url)
    return RedirectResponse(auth_url)


async def _callback_endpoint(request: Request) -> HTMLResponse:
    """Handle OAuth callback from Adobe IMS.

    Query parameters:
        code: Authorization code (present on success)
        state: Signed state token (required)
        error: Error code (present on failure)

    Returns:
        HTML page with success or error message.
    """
    # Get components from app state
    token_manager: TokenManager = request.app.state.token_manager
    state_serializer: StateSerializer = request.app.state.state_serializer

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    # Check for OAuth error
    if error:
        error_description = request.query_params.get("error_description", "Unknown error")
        error_escaped = html.escape(error)
        error_description_escaped = html.escape(error_description)
        return HTMLResponse(
            f"""
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p><strong>Error:</strong> {error_escaped}</p>
                <p><strong>Description:</strong> {error_description_escaped}</p>
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

    # Verify and decode state token (stateless - no storage lookup needed)
    try:
        state_data = state_serializer.loads(state)
    except SignatureExpired:
        return HTMLResponse(
            """
            <html>
            <head><title>Session Expired</title></head>
            <body>
                <h1>Session Expired</h1>
                <p>The authentication session has expired.</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )
    except BadSignature:
        return HTMLResponse(
            """
            <html>
            <head><title>Invalid State</title></head>
            <body>
                <h1>Invalid State</h1>
                <p>The authentication state token is invalid.</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )

    user_id = state_data.get("user_id")
    redirect_url = state_data.get("redirect_url")

    if not user_id or not redirect_url:
        return HTMLResponse(
            """
            <html>
            <head><title>Invalid State Data</title></head>
            <body>
                <h1>Invalid State Data</h1>
                <p>The authentication state is incomplete or corrupted.</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Get shared OAuth client from app state
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client

    try:
        # Exchange code for tokens using the same redirect URL
        token_data = await oauth_client.exchange_code(code, redirect_url)
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
                </style>
            </head>
            <body>
                <div class="container">
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
    except Exception:
        logger.exception("OAuth token exchange failed")
        return HTMLResponse(
            """
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>An error occurred during authentication.</p>
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
