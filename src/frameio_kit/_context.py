"""Request context management for user authentication and install configuration.

This module provides request-scoped context variables for storing sensitive
authentication data, install configuration, and the underlying request object
without attaching them to event objects.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

# Context variable for storing the underlying FastAPI Request object
# This is set automatically when processing webhook and action handler requests
_request_context: ContextVar[Request | None] = ContextVar("request", default=None)

# Context variable for storing the authenticated user's access token
# This is set automatically when processing user-authenticated actions
_user_token_context: ContextVar[str | None] = ContextVar("user_token", default=None)

# Context variable for storing the installation config for the current request
# This is set automatically when processing events for an app with install_fields
_install_config_context: ContextVar[dict[str, str] | None] = ContextVar("install_config", default=None)


def get_request() -> Request:
    """Get the underlying FastAPI Request object for the current handler invocation.

    This function provides access to the raw request, which is useful for reading
    headers, client IP, cookies, query parameters, or other HTTP-level details not
    exposed through the event object.

    Returns:
        The FastAPI ``Request`` for the current handler invocation.

    Raises:
        RuntimeError: If called outside a webhook or action handler context.

    Example:
        ```python
        from frameio_kit import App, get_request, WebhookEvent

        @app.on_webhook("file.ready")
        async def on_file_ready(event: WebhookEvent):
            request = get_request()
            client_ip = request.client.host
            user_agent = request.headers.get("user-agent")
        ```
    """
    request = _request_context.get()
    if request is None:
        raise RuntimeError("get_request() can only be called within a webhook or action handler.")
    return request


def get_user_token() -> str:
    """Get the authenticated user's access token.

    This function retrieves the OAuth access token for the currently authenticated
    user. It can only be called within an action handler that has user authentication
    enabled (require_user_auth=True).

    The token is stored in request-scoped context, not on the event object, to
    prevent accidental logging or exposure of sensitive credentials.

    Returns:
        The user's OAuth access token string.

    Raises:
        RuntimeError: If called outside a user-authenticated action context.

    Example:
        ```python
        from frameio_kit import App, get_user_token, Client

        @app.on_action(..., require_user_auth=True)
        async def process_file(event: ActionEvent):
            # Get the user's token
            token = get_user_token()

            # Use it with the built-in Client
            async with Client(token=token) as user_client:
                ...

            # Or pass to other services
            await external_service.authenticate(token)
        ```
    """
    token = _user_token_context.get()
    if token is None:
        raise RuntimeError(
            "get_user_token() can only be called within a user-authenticated action handler. "
            "Ensure the action was registered with require_user_auth=True."
        )
    return token


def get_install_config() -> dict[str, str]:
    """Get the installation configuration for the current request.

    This function retrieves the config values collected during app installation.
    It can only be called within a webhook or action handler for an app that
    has ``install_fields`` configured and an existing installation.

    The config is stored in request-scoped context, not on the event object.

    Returns:
        A dict mapping field names to their string values.

    Raises:
        RuntimeError: If called outside an install-configured handler context.

    Example:
        ```python
        from frameio_kit import App, get_install_config, InstallField

        app = App(
            install=True,
            install_fields=[
                InstallField(name="api_key", label="API Key", type="password", required=True),
            ],
        )

        @app.on_webhook("file.ready")
        async def on_file_ready(event):
            config = get_install_config()
            api_key = config["api_key"]
        ```
    """
    config = _install_config_context.get()
    if config is None:
        raise RuntimeError(
            "get_install_config() requires install_fields, an existing installation, "
            "and stored install config for this workspace."
        )
    return config
