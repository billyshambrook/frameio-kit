"""Request context management for user authentication and install configuration.

This module provides request-scoped context variables for storing sensitive
authentication data and install configuration without attaching them to event objects.
"""

from contextvars import ContextVar

# Context variable for storing the authenticated user's access token
# This is set automatically when processing user-authenticated actions
_user_token_context: ContextVar[str | None] = ContextVar("user_token", default=None)

# Context variable for storing the installation config for the current request
# This is set automatically when processing events for an app with install_fields
_install_config_context: ContextVar[dict[str, str] | None] = ContextVar("install_config", default=None)


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
