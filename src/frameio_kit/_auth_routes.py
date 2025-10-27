"""OAuth authentication routes for Adobe IMS integration.

This module provides OAuth 2.0 endpoints for the authorization code flow,
including login initiation and callback handling with CSRF protection.
"""

import secrets
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from ._oauth import AdobeOAuthClient, TokenManager


async def _login_endpoint(request: Request) -> RedirectResponse | HTMLResponse:
    """Initiate OAuth flow by redirecting to Adobe IMS.

    Query parameters:
        user_id: Frame.io user ID (required)
        interaction_id: Frame.io interaction ID for multi-step flows (optional)

    Returns:
        Redirect to Adobe IMS authorization page.
    """
    # Get oauth client and token manager from app state
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client
    token_manager: TokenManager = request.app.state.token_manager

    # Extract user context from query params
    user_id = request.query_params.get("user_id")
    interaction_id = request.query_params.get("interaction_id")

    if not user_id:
        return HTMLResponse(
            "<h1>Error</h1><p>Missing user_id parameter</p>",
            status_code=400,
        )

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)

    # Store state in storage backend with 10-minute TTL (600 seconds)
    state_data: dict[str, Any] = {
        "user_id": user_id,
        "interaction_id": interaction_id,
    }
    state_key = f"oauth_state:{state}"
    await token_manager.storage.put(state_key, state_data, ttl=600)

    # Redirect to Adobe OAuth
    auth_url = oauth_client.get_authorization_url(state)
    return RedirectResponse(auth_url)


async def _callback_endpoint(request: Request) -> HTMLResponse:
    """Handle OAuth callback from Adobe IMS.

    Query parameters:
        code: Authorization code (present on success)
        state: CSRF state token (required)
        error: Error code (present on failure)

    Returns:
        HTML page with success or error message.
    """
    # Get token manager and oauth client from app state
    token_manager: TokenManager = request.app.state.token_manager
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client

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

    # Delete state after retrieval (consume once)
    await token_manager.storage.delete(state_key)

    user_id = state_data["user_id"]

    try:
        # Exchange code for tokens
        token_data = await oauth_client.exchange_code(code)
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


def create_auth_routes(token_manager: TokenManager, oauth_client: AdobeOAuthClient) -> list[Route]:
    """Create OAuth authentication routes.

    Args:
        token_manager: TokenManager instance for storing tokens.
        oauth_client: AdobeOAuthClient for OAuth operations.

    Returns:
        List of Starlette Route objects to mount in the app.

    Note:
        These routes will be mounted at:
        - GET /auth/login - Initiates OAuth flow
        - GET /auth/callback - Handles OAuth callback

    Example:
        ```python
        from starlette.applications import Starlette

        app = Starlette()
        auth_routes = create_auth_routes(token_manager, oauth_client)
        app.routes.extend(auth_routes)
        ```
    """
    return [
        Route("/auth/login", _login_endpoint, methods=["GET"]),
        Route("/auth/callback", _callback_endpoint, methods=["GET"]),
    ]
