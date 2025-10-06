"""The central module for the Frame.io SDK application.

This module contains the `App` class, which is the main entry point for any
developer building an integration. It acts as both an ASGI-compliant web
application and a registry for event handlers.

A developer typically instantiates this class once in their main script, uses its
decorator methods (`@app.on_webhook`, `@app.on_action`) to register functions that
respond to Frame.io events, and then runs it with an ASGI server like Uvicorn.

Example:
    ```python
    # main.py
    import os

    import uvicorn
    from frameio_kit.app import App
    from frameio_kit.events import WebhookEvent
    from frameio_kit.ui import Message

    # Initialize the app, optionally with a token for API calls
    app = App(token=os.getenv("FRAMEIO_TOKEN"))

    @app.on_webhook("file.ready", secret=os.getenv("WEBHOOK_SECRET"))
    async def on_file_ready(event: WebhookEvent):
        print(f"File '{event.resource_id}' is now ready!")
        return Message(title="Processing Started", description="File received.")

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)
    ```
"""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncGenerator, Awaitable, Callable, cast

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from .client import Client
from .events import ActionEvent, WebhookEvent
from .oauth import OAuthManager, RequireAuth, TokenStore
from .security import verify_signature
from .ui import Form, Message

# --- Handler Type Definitions ---

# A handler for a standard webhook, which is non-interactive.
# It can only return a Message or nothing.
WebhookHandlerFunc = Callable[[WebhookEvent], Awaitable[Message | None]]

# A handler for a custom action, which is interactive.
# It can return a Message, a Form for further input, RequireAuth for OAuth, or nothing.
ActionHandlerFunc = Callable[[ActionEvent], Awaitable[Message | Form | RequireAuth | None]]


@dataclass
class _HandlerRegistration:
    """Stores metadata for a registered webhook or action handler."""

    func: WebhookHandlerFunc | ActionHandlerFunc
    secret: str
    name: str | None = None
    description: str | None = None
    model: type[WebhookEvent | ActionEvent] = field(default=WebhookEvent)


class App:
    """The main application class for building Frame.io integrations.

    This class serves as the core of your integration. It is an ASGI-compatible
    application that listens for incoming HTTP POST requests from Frame.io,
    validates their signatures, and dispatches them to the appropriate handler
    functions that you register using decorators.

    Attributes:
        client: An authenticated API client for making calls back to the
            Frame.io API, available if an `token` was provided.
        oauth: An OAuth manager for user authorization flows, available if
            OAuth credentials were provided.
    """

    def __init__(
        self,
        token: str | None = None,
        oauth_client_id: str | None = None,
        oauth_client_secret: str | None = None,
        oauth_redirect_uri: str | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        """Initializes the FrameApp.

        Args:
            token: An optional access token obtained from the Adobe Developer
                Console. If provided, this token will be used to authenticate
                API calls made via the `app.client` property. It is highly
                recommended to load this from a secure source, such as an
                environment variable.
            oauth_client_id: OAuth client ID for user authorization flows.
            oauth_client_secret: OAuth client secret for user authorization flows.
            oauth_redirect_uri: The redirect URI for OAuth callbacks.
            token_store: Custom token storage implementation for persisting
                user tokens.
        """
        self._token = token
        self._api_client: Client | None = None
        self._webhook_handlers: dict[str, _HandlerRegistration] = {}
        self._action_handlers: dict[str, _HandlerRegistration] = {}
        self._oauth_manager: OAuthManager | None = None

        # Initialize OAuth manager if credentials are provided
        if oauth_client_id and oauth_client_secret and oauth_redirect_uri:
            self._oauth_manager = OAuthManager(
                client_id=oauth_client_id,
                client_secret=oauth_client_secret,
                redirect_uri=oauth_redirect_uri,
                token_store=token_store,
            )

        self._asgi_app = self._create_asgi_app()

    @property
    def client(self) -> Client:
        """Provides access to an authenticated asynchronous API client.

        This client can be used within your handler functions to make calls back
        to the Frame.io API to fetch more information or perform actions. The
        client is initialized lazily on its first access.

        Example:
            ```python
            @app.on_webhook("file.ready", secret="...")
            async def on_file_ready(event: WebhookEvent):
                # Use the client to fetch more details about the file
                file_details = await app.client.files.get(event.resource_id)
                print(file_details.name)
            ```

        Returns:
            An instance of Frame.io `Client`, ready to make authenticated requests.

        Raises:
            RuntimeError: If the `App` was initialized without an `token`.
        """
        if not self._token:
            raise RuntimeError("Cannot access API client. `token` was not provided to App.")
        if self._api_client is None:
            self._api_client = Client(token=self._token)
        return self._api_client

    @property
    def oauth(self) -> OAuthManager:
        """Provides access to the OAuth manager for user authorization.

        This property gives access to OAuth functionality for obtaining user
        tokens. Use this to generate authorization URLs and handle token exchange.

        Example:
            ```python
            @app.on_action("my_action", name="My Action", ...)
            async def handle_action(event: ActionEvent):
                # Generate an authorization URL for the user
                auth_url = app.oauth.get_authorization_url(
                    state=f"{event.user.id}:{event.interaction_id}"
                )
                return Form(
                    title="Authorization Required",
                    description="Please authorize to continue",
                    fields=[LinkField(label="Authorize", name="auth", value=auth_url)]
                )
            ```

        Returns:
            The OAuthManager instance.

        Raises:
            RuntimeError: If OAuth credentials were not provided to App.
        """
        if not self._oauth_manager:
            raise RuntimeError(
                "OAuth not configured. Provide oauth_client_id, oauth_client_secret, "
                "and oauth_redirect_uri when initializing App."
            )
        return self._oauth_manager

    async def get_user_client(self, user_id: str) -> Client:
        """Create an API client authenticated with a user's token.

        This method retrieves the stored token for a user and creates a Client
        instance that makes API calls on behalf of that user.

        Args:
            user_id: The Frame.io user ID.

        Returns:
            A Client instance authenticated with the user's access token.

        Raises:
            RuntimeError: If OAuth is not configured or no token is found for the user.
        """
        token = await self.oauth.get_user_token(user_id)
        if not token:
            raise RuntimeError(f"No token found for user {user_id}. User needs to authorize.")
        return Client(token=token)

    def on_webhook(self, event_type: str | list[str], secret: str):
        """Decorator to register a function as a webhook event handler.

        This decorator registers an asynchronous function to be called whenever
        Frame.io sends a webhook event of the specified type(s). A webhook
        handler can only receive `WebhookEvent` and can only return a `Message`
        or `None`.

        Args:
            event_type: The Frame.io event type to listen for (e.g.,
                `"file.ready"`). You can also provide a list of strings to
                register the same handler for multiple event types.
            secret: The mandatory signing secret obtained from the Frame.io
                Developer Console for this webhook. It is used to verify the
                authenticity of incoming requests.
        """

        def decorator(func: WebhookHandlerFunc):
            events = [event_type] if isinstance(event_type, str) else event_type
            for event in events:
                self._webhook_handlers[event] = _HandlerRegistration(func=func, secret=secret, model=WebhookEvent)
            return func

        return decorator

    def on_action(self, event_type: str, name: str, description: str, secret: str):
        """Decorator to register a function as a custom action handler.

        This decorator connects an asynchronous function to a Custom Action in the
        Frame.io UI. The handler receives an `ActionEvent` and can return a
        `Message`, a `Form` for more input, or `None`.

        Args:
            event_type: A unique string you define to identify this action
                (e.g., `"my_app.transcribe"`). This is the `type` that will be
                present in the incoming payload.
            name: The user-visible name for the action in the Frame.io UI menu.
            description: A short, user-visible description of what the action does.
            secret: The mandatory signing secret generated when you create the
                custom action in Frame.io.
        """

        def decorator(func: ActionHandlerFunc):
            self._action_handlers[event_type] = _HandlerRegistration(
                func=func, secret=secret, name=name, description=description, model=ActionEvent
            )
            return func

        return decorator

    @asynccontextmanager
    async def _lifespan(self, app: Starlette) -> AsyncGenerator[None, None]:
        """Manages the application's lifespan, including client setup and teardown."""
        if self._token:
            _ = self.client  # Initialize the client

        yield

        if self._api_client:
            await self._api_client.close()
        if self._oauth_manager:
            await self._oauth_manager.close()

    def _create_asgi_app(self) -> Starlette:
        """Builds the Starlette ASGI application with routes and lifecycle hooks."""
        routes = [Route("/", self._handle_request, methods=["POST"])]
        
        # Add OAuth callback route if OAuth is configured
        if self._oauth_manager:
            routes.append(Route("/oauth/callback", self._handle_oauth_callback, methods=["GET"]))
        
        return Starlette(
            debug=True,
            routes=routes,
            lifespan=self._lifespan,
        )

    def _find_handler(self, event_type: str) -> _HandlerRegistration | None:
        """Finds the registered handler for a given event type."""
        return self._webhook_handlers.get(event_type) or self._action_handlers.get(event_type)

    async def _handle_oauth_callback(self, request: Request) -> Response:
        """Handles the OAuth callback from Frame.io.
        
        This endpoint receives the authorization code from Frame.io and exchanges
        it for access and refresh tokens, then stores them using the configured
        token store.
        """
        if not self._oauth_manager:
            return Response("OAuth not configured.", status_code=500)

        # Get the authorization code and state from query parameters
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            return Response(f"OAuth error: {error}", status_code=400)

        if not code:
            return Response("Missing authorization code.", status_code=400)

        try:
            # Exchange the code for tokens
            token_data = await self._oauth_manager.exchange_code_for_token(code)

            # Parse the state to get user_id if included
            # State format should be "user_id:interaction_id" or just "user_id"
            user_id = None
            if state:
                user_id = state.split(":")[0]

            # Store the token if we have a user_id and token store
            if user_id and self._oauth_manager.token_store:
                await self._oauth_manager.token_store.save_token(
                    user_id, token_data.model_dump()
                )

            return Response(
                "Authorization successful! You can close this window and return to Frame.io.",
                status_code=200,
            )

        except Exception as e:
            print(f"Error during OAuth callback: {e}")
            return Response("OAuth authorization failed.", status_code=500)

    async def _handle_request(self, request: Request) -> Response:
        """The main ASGI request handler, refactored for clarity."""
        body = await request.body()
        try:
            payload = json.loads(body)
            event_type = payload.get("type")
        except (json.JSONDecodeError, AttributeError):
            return Response("Invalid JSON payload.", status_code=400)

        if not event_type:
            return Response("Payload missing 'type' field.", status_code=400)

        handler_reg = self._find_handler(event_type)
        if not handler_reg:
            return Response(f"No handler registered for event type '{event_type}'.", status_code=404)

        if not await verify_signature(request.headers, body, handler_reg.secret):
            return Response("Invalid signature.", status_code=401)

        try:
            event = handler_reg.model.model_validate(payload)

            if handler_reg.model is WebhookEvent:
                webhook_handler = cast(WebhookHandlerFunc, handler_reg.func)
                response_data = await webhook_handler(cast(WebhookEvent, event))
            else:
                action_handler = cast(ActionHandlerFunc, handler_reg.func)
                response_data = await action_handler(cast(ActionEvent, event))

            # Handle RequireAuth response - automatically generate auth message
            if isinstance(response_data, RequireAuth):
                if not self._oauth_manager:
                    return Response(
                        "OAuth not configured. Cannot handle RequireAuth response.",
                        status_code=500
                    )
                
                # Cast event to ActionEvent for OAuth flow
                action_event = cast(ActionEvent, event)
                
                # Generate authorization URL
                auth_url = self._oauth_manager.get_authorization_url(
                    state=f"{action_event.user.id}:{action_event.interaction_id}"
                )
                
                # Construct the authorization message
                title = response_data.title or "Authorization Required"
                
                if response_data.description:
                    # User provided custom description - append auth URL
                    description = (
                        f"{response_data.description}\n\n"
                        f"Please visit this URL to authorize: {auth_url}\n\n"
                        f"After authorizing, trigger this action again."
                    )
                else:
                    # Use default description
                    description = (
                        f"This action requires your authorization to access your Frame.io account.\n\n"
                        f"Please visit this URL to authorize: {auth_url}\n\n"
                        f"After authorizing, trigger this action again."
                    )
                
                auth_message = Message(title=title, description=description)
                return JSONResponse(auth_message.model_dump(exclude_none=True))

            if isinstance(response_data, Message) or isinstance(response_data, Form):
                return JSONResponse(response_data.model_dump(exclude_none=True))

            return Response("OK", status_code=200)

        except ValidationError as e:
            return Response(f"Payload validation error: {e}", status_code=422)
        except Exception as e:
            print(f"Error processing event '{event_type}': {e}")
            return Response("Internal Server Error", status_code=500)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """ASGI call interface to delegate to the underlying Starlette app."""
        await self._asgi_app(scope, receive, send)
