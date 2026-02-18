"""OAuth authentication routes for Adobe IMS integration.

This module provides OAuth 2.0 endpoints for the authorization code flow,
including login initiation and callback handling using stateless signed tokens.
"""

import logging
from typing import Callable, TypedDict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired

from ._context import _user_token_context
from ._oauth import get_oauth_redirect_url
from ._state import _AppState, _require

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


def create_auth_routes(get_state: Callable[[], _AppState]) -> APIRouter:
    """Create OAuth authentication routes.

    Args:
        get_state: A callable (suitable for ``Depends()``) that returns the
            shared ``_AppState`` instance.

    Returns:
        An ``APIRouter`` with the following routes:

        - GET /auth/login - Initiates OAuth flow
        - GET /auth/callback - Handles OAuth callback

    Example:
        ```python
        from fastapi import FastAPI

        app = FastAPI()
        router = create_auth_routes(get_state)
        app.include_router(router)
        ```
    """
    router = APIRouter()

    @router.get("/auth/login", response_model=None)
    async def _login_endpoint(request: Request, state: _AppState = Depends(get_state)):
        """Initiate OAuth flow by redirecting to Adobe IMS.

        Query parameters:
            user_id: Frame.io user ID (required)
            interaction_id: Frame.io interaction ID for multi-step flows (optional)
            action_type: Custom action event type for on_auth_complete callback routing (optional)

        Returns:
            Redirect to Adobe IMS authorization page.
        """

        # Get oauth config from app state
        oauth_config = _require(state.oauth_config)
        state_serializer = _require(state.state_serializer)
        renderer = _require(state.auth_renderer)

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
        oauth_client = _require(state.oauth_client)

        # Create signed state token with embedded data (stateless - no storage needed)
        state_data: OAuthStateData = {
            "user_id": user_id,
            "interaction_id": interaction_id,
            "redirect_url": redirect_url,
            "action_type": action_type,
        }
        signed_state = state_serializer.dumps(state_data)

        # Redirect to Adobe OAuth
        auth_url = oauth_client.get_authorization_url(signed_state, redirect_url)
        return RedirectResponse(auth_url)

    @router.get("/auth/callback", response_model=None)
    async def _callback_endpoint(request: Request, state: _AppState = Depends(get_state)):
        """Handle OAuth callback from Adobe IMS.

        Query parameters:
            code: Authorization code (present on success)
            state: Signed state token (required)
            error: Error code (present on failure)

        Returns:
            HTML page with success or error message.
        """

        # Get components from app state
        token_manager = _require(state.token_manager)
        state_serializer = _require(state.state_serializer)
        renderer = _require(state.auth_renderer)

        code = request.query_params.get("code")
        state_param = request.query_params.get("state")
        error = request.query_params.get("error")

        # Check for OAuth error
        if error:
            error_description = request.query_params.get("error_description", "Unknown error")
            return HTMLResponse(
                renderer.render_error("Authentication Failed", error_description),
                status_code=400,
            )

        # Validate required parameters
        if not code or not state_param:
            return HTMLResponse(
                renderer.render_error("Invalid Request", "Missing code or state parameter."),
                status_code=400,
            )

        # Verify and decode state token (stateless - no storage lookup needed)
        try:
            state_data = state_serializer.loads(state_param)
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
        oauth_client = _require(state.oauth_client)

        try:
            # Exchange code for tokens using the same redirect URL
            token_data = await oauth_client.exchange_code(code, redirect_url)
            await token_manager.store_token(user_id, token_data)

            # Check for on_auth_complete callback
            action_type = state_data.get("action_type")
            if action_type:
                try:
                    action_handlers = state.action_handlers or {}
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
                                        "on_auth_complete returned non-Response value of type %r; "
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

    return router
