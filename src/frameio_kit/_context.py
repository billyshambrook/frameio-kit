"""Request context management for user authentication.

This module provides request-scoped context variables for storing sensitive
authentication data without attaching it to event objects.
"""

from contextvars import ContextVar

# Context variable for storing the authenticated user's access token
# This is set automatically when processing user-authenticated actions
_user_token_context: ContextVar[str | None] = ContextVar("user_token", default=None)


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
            user_client = Client(token=token)

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
