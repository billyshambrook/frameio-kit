"""OAuth authentication routes for Adobe IMS integration.

This module provides OAuth 2.0 endpoints for the authorization code flow,
including login initiation and callback handling using stateless signed tokens.
"""

import logging
from typing import TypedDict

from itsdangerous import BadSignature, SignatureExpired
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ._context import _user_token_context
from ._oauth import AdobeOAuthClient, OAuthConfig, StateSerializer, TokenManager, get_oauth_redirect_url

logger = logging.getLogger(__name__)


class OAuthStateData(TypedDict):
    """Typed dictionary for OAuth state data embedded in signed tokens.

    Attributes:
        user_id: Frame.io user ID initiating the auth flow.
        interaction_id: Optional interaction ID for multi-step flows.
        redirect_url: OAuth redirect URL to use for the callback.
        action_type: Optional action type that triggered the auth flow.
    """

    user_id: str
    interaction_id: str | None
    redirect_url: str
    action_type: str | None


async def _login_endpoint(request: Request) -> RedirectResponse | HTMLResponse:
    """Initiate OAuth flow by redirecting to Adobe IMS.

    Query parameters:
        user_id: Frame.io user ID (required)
        interaction_id: Frame.io interaction ID for multi-step flows (optional)
        action_type: Custom action event type for on_auth_complete callback routing (optional)

    Returns:
        Redirect to Adobe IMS authorization page.
    """
    from ._auth_templates import AuthTemplateRenderer

    # Get oauth config from app state
    oauth_config: OAuthConfig = request.app.state.oauth_config
    state_serializer: StateSerializer = request.app.state.state_serializer
    renderer: AuthTemplateRenderer = request.app.state.auth_renderer

    # Extract user context from query params
    user_id = request.query_params.get("user_id")
    interaction_id = request.query_params.get("interaction_id")
    action_type = request.query_params.get("action_type")

    if not user_id:
        return HTMLResponse(
            renderer.render_error("Invalid Request", "Missing user_id parameter"),
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
        "action_type": action_type,
    }
    state = state_serializer.dumps(state_data)

    # Redirect to Adobe OAuth
    auth_url = oauth_client.get_authorization_url(state, redirect_url)
    return RedirectResponse(auth_url)


async def _callback_endpoint(request: Request) -> HTMLResponse | Response:
    """Handle OAuth callback from Adobe IMS.

    Query parameters:
        code: Authorization code (present on success)
        state: Signed state token (required)
        error: Error code (present on failure)

    Returns:
        HTML page with success or error message.
    """
    from ._auth_templates import AuthTemplateRenderer

    # Get components from app state
    token_manager: TokenManager = request.app.state.token_manager
    state_serializer: StateSerializer = request.app.state.state_serializer
    renderer: AuthTemplateRenderer = request.app.state.auth_renderer

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    # Check for OAuth error
    if error:
        error_description = request.query_params.get("error_description", "Unknown error")
        return HTMLResponse(
            renderer.render_error("Authentication Failed", error_description),
            status_code=400,
        )

    # Validate required parameters
    if not code or not state:
        return HTMLResponse(
            renderer.render_error("Invalid Request", "Missing code or state parameter."),
            status_code=400,
        )

    # Verify and decode state token (stateless - no storage lookup needed)
    try:
        state_data = state_serializer.loads(state)
    except SignatureExpired:
        return HTMLResponse(
            renderer.render_error("Session Expired", "The authentication session has expired."),
            status_code=400,
        )
    except BadSignature:
        return HTMLResponse(
            renderer.render_error("Invalid State", "The authentication state token is invalid."),
            status_code=400,
        )

    user_id = state_data.get("user_id")
    redirect_url = state_data.get("redirect_url")

    if not user_id or not redirect_url:
        return HTMLResponse(
            renderer.render_error("Invalid State Data", "The authentication state is incomplete."),
            status_code=400,
        )

    # Get shared OAuth client from app state
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client

    try:
        # Exchange code for tokens using the same redirect URL
        token_data = await oauth_client.exchange_code(code, redirect_url)
        await token_manager.store_token(user_id, token_data)

        # Check for on_auth_complete callback
        action_type = state_data.get("action_type")
        if action_type:
            try:
                action_handlers = getattr(request.app.state, "_action_handlers", {})
                handler_reg = action_handlers.get(action_type)
                if handler_reg and handler_reg.on_auth_complete:
                    interaction_id = state_data.get("interaction_id")
                    if interaction_id is None:
                        logger.warning("on_auth_complete skipped: interaction_id missing from OAuth state")
                    else:
                        storage = token_manager.storage
                        storage_key = f"pending_auth:{user_id}:{interaction_id}"
                        event_data = await storage.get(storage_key)
                        if event_data:
                            await storage.delete(storage_key)
                            from ._app import AuthCompleteContext
                            from ._events import ActionEvent

                            event = ActionEvent.model_validate(event_data)
                            ctx = AuthCompleteContext(event=event)
                            token_ctx = _user_token_context.set(token_data.access_token)
                            try:
                                result = await handler_reg.on_auth_complete(ctx)
                            finally:
                                _user_token_context.reset(token_ctx)
                            if isinstance(result, Response):
                                return result
                            if result is not None:
                                logger.warning(
                                    "on_auth_complete returned non-Response value %r; "
                                    "falling through to default success page",
                                    type(result),
                                )
                        else:
                            logger.warning(
                                "Stored event not found for pending_auth:%s:%s "
                                "(may have expired); falling through to default success page",
                                user_id,
                                interaction_id,
                            )
            except Exception:
                logger.exception("on_auth_complete callback failed; falling through to default success page")

        return HTMLResponse(renderer.render_success())
    except Exception:
        logger.exception("OAuth token exchange failed")
        return HTMLResponse(
            renderer.render_error("Authentication Failed", "An error occurred during authentication."),
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
