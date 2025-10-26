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

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)
    ```
"""

import functools
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

from ._auth_routes import create_auth_routes
from ._client import Client
from ._encryption import TokenEncryption
from ._events import ActionEvent, AnyEvent, WebhookEvent
from ._middleware import Middleware
from ._oauth import AdobeOAuthClient, OAuthConfig, TokenManager
from ._responses import AnyResponse, Form, Message
from ._security import verify_signature

# A handler for a standard webhook, which is non-interactive.
# It can only return a Message or nothing.
WebhookHandlerFunc = Callable[[WebhookEvent], Awaitable[None]]

# A handler for a custom action, which is interactive.
# It can return a Message, a Form for further input, or nothing.
ActionHandlerFunc = Callable[[ActionEvent], Awaitable[AnyResponse]]


@dataclass
class _HandlerRegistration:
    """Stores metadata for a registered webhook or action handler."""

    func: WebhookHandlerFunc | ActionHandlerFunc
    secret: str
    name: str | None = None
    description: str | None = None
    model: type[AnyEvent] = field(default=WebhookEvent)
    require_user_auth: bool = False


class App:
    """The main application class for building Frame.io integrations.

    This class serves as the core of your integration. It is an ASGI-compatible
    application that listens for incoming HTTP POST requests from Frame.io,
    validates their signatures, and dispatches them to the appropriate handler
    functions that you register using decorators.

    Attributes:
        client: An authenticated API client for making calls back to the
            Frame.io API, available if an `token` was provided.
    """

    def __init__(
        self, *, token: str | None = None, middleware: list[Middleware] = [], oauth: OAuthConfig | None = None
    ) -> None:
        """Initializes the FrameApp.

        Args:
            token: An optional access token obtained from the Adobe Developer
                Console. If provided, this token will be used to authenticate
                API calls made via the `app.client` property. It is highly
                recommended to load this from a secure source, such as an
                environment variable.
            middleware: An optional list of middleware classes to process
                requests before they reach the handler.
            oauth: Optional OAuth configuration for user authentication. When
                provided, enables Adobe Login OAuth flow for actions that
                require user-specific authentication.
        """
        self._token = token
        self._middleware = middleware or []
        self._oauth_config = oauth
        self._api_client: Client | None = None
        self._webhook_handlers: dict[str, _HandlerRegistration] = {}
        self._action_handlers: dict[str, _HandlerRegistration] = {}

        # Initialize OAuth components if configured
        self._oauth_client: AdobeOAuthClient | None = None
        self._token_manager: TokenManager | None = None
        if self._oauth_config:
            self._oauth_client = AdobeOAuthClient(
                client_id=self._oauth_config.client_id,
                client_secret=self._oauth_config.client_secret,
                redirect_uri=self._oauth_config.redirect_uri,
                scopes=self._oauth_config.scopes,
            )
            # Use provided storage or default to MemoryStore
            storage = self._oauth_config.storage
            if storage is None:
                from key_value.aio.stores.memory import MemoryStore

                storage = MemoryStore()

            encryption = TokenEncryption(key=self._oauth_config.encryption_key)
            self._token_manager = TokenManager(storage=storage, encryption=encryption, oauth_client=self._oauth_client)

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
                file_details = await app.client.files.show(account_id=event.account_id, file_id=event.resource_id)
                print(file_details.data.name)
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
    def token_manager(self) -> TokenManager:
        """Provides access to the OAuth token manager.

        This manager handles encrypted token storage, retrieval, and automatic
        refresh for user authentication. Only available when OAuth is configured.

        Example:
            ```python
            # Delete a user's token (logout)
            await app.token_manager.delete_token(user_id="user_123")

            # Check if user has a token
            token = await app.token_manager.get_token(user_id="user_123")
            if token:
                print("User is authenticated")
            ```

        Returns:
            The TokenManager instance for managing user tokens.

        Raises:
            RuntimeError: If OAuth was not configured during App initialization.
        """
        if not self._token_manager:
            raise RuntimeError("Cannot access token manager. OAuth not configured in App initialization.")
        return self._token_manager

    def on_webhook(self, event_type: str | list[str], secret: str):
        """Decorator to register a function as a webhook event handler.

        This decorator registers an asynchronous function to be called whenever
        Frame.io sends a webhook event of the specified type(s). A webhook
        handler can only receive `WebhookEvent` and can only return a `Message`
        or `None`.

        Example:
            ```python
            from frameio_kit import App, WebhookEvent

            app = App()

            @app.on_webhook(event_type="file.ready", secret="your-secret")
            async def on_file_ready(event: WebhookEvent):
                # Handle the event
                pass
            ```

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

    def on_action(self, event_type: str, name: str, description: str, secret: str, *, require_user_auth: bool = False):
        """Decorator to register a function as a custom action handler.

        This decorator connects an asynchronous function to a Custom Action in the
        Frame.io UI. The handler receives an `ActionEvent` and can return a
        `Message`, a `Form` for more input, or `None`.

        Example:
            ```python
            from frameio_kit import App, ActionEvent

            app = App()

            @app.on_action(event_type="my_app.transcribe", name="Transcribe", description="Transcribe file", secret="your-secret")
            async def on_transcribe(event: ActionEvent):
                # Handle the event
                pass
            ```

        Args:
            event_type: A unique string you define to identify this action
                (e.g., `"my_app.transcribe"`). This is the `type` that will be
                present in the incoming payload.
            name: The user-visible name for the action in the Frame.io UI menu.
            description: A short, user-visible description of what the action does.
            secret: The mandatory signing secret generated when you create the
                custom action in Frame.io.
            require_user_auth: If True, requires user to authenticate via Adobe
                Login OAuth before executing the handler. OAuth must be configured
                in App initialization for this to work.
        """

        def decorator(func: ActionHandlerFunc):
            self._action_handlers[event_type] = _HandlerRegistration(
                func=func,
                secret=secret,
                name=name,
                description=description,
                model=ActionEvent,
                require_user_auth=require_user_auth,
            )
            return func

        return decorator

    @asynccontextmanager
    async def _lifespan(self, app: Starlette) -> AsyncGenerator[None, None]:
        """Manages the application's lifespan, including client setup and teardown."""
        if self._token:
            _ = self.client  # Initialize the client

        # Store OAuth components in app state for route access
        if self._oauth_client and self._token_manager:
            app.state.oauth_client = self._oauth_client
            app.state.token_manager = self._token_manager

        yield

        if self._api_client:
            await self._api_client.close()

        if self._oauth_client:
            await self._oauth_client.close()

    def _create_asgi_app(self) -> Starlette:
        """Builds the Starlette ASGI application with routes and lifecycle hooks."""
        routes = [Route("/", self._handle_request, methods=["POST"])]

        # Add OAuth routes if configured
        if self._oauth_client and self._token_manager:
            auth_routes = create_auth_routes(self._token_manager, self._oauth_client)
            routes.extend(auth_routes)

        return Starlette(
            debug=True,
            routes=routes,
            lifespan=self._lifespan,
        )

    def _find_handler(self, event_type: str) -> _HandlerRegistration | None:
        """Finds the registered handler for a given event type."""
        return self._webhook_handlers.get(event_type) or self._action_handlers.get(event_type)

    def _create_login_form(self, event: ActionEvent) -> Form:
        """Create a Form prompting the user to authenticate.

        Args:
            event: The ActionEvent that triggered the auth request.

        Returns:
            A Form with a link to initiate the OAuth flow.
        """
        from ._responses import LinkField

        # Build login URL with user context
        login_url = f"/.auth/login?user_id={event.user_id}"
        if event.interaction_id:
            login_url += f"&interaction_id={event.interaction_id}"

        return Form(
            title="Authentication Required",
            description="Please click the link below to sign in with Adobe and continue.",
            fields=[
                LinkField(
                    label="Sign in with Adobe",
                    name="login_url",
                    value=login_url,
                )
            ],
        )

    def _build_middleware_chain(
        self, handler: Callable[[AnyEvent], Awaitable[AnyResponse]]
    ) -> Callable[[AnyEvent], Awaitable[AnyResponse]]:
        wrapped = handler
        for mw in reversed(self._middleware):
            wrapped = functools.partial(mw.__call__, next=wrapped)
        return wrapped

    async def _check_user_auth(self, event: ActionEvent) -> Form | None:
        """Check if user is authenticated and return login form if not.

        Args:
            event: The ActionEvent to check authentication for.

        Returns:
            Login Form if user needs to authenticate, None if authenticated.

        Raises:
            RuntimeError: If OAuth not configured but auth required.
        """
        if not self._token_manager:
            raise RuntimeError("User authentication required but OAuth not configured.")

        # Check if user has a valid token
        user_token_data = await self._token_manager.get_token(event.user_id)
        if not user_token_data:
            # User not authenticated - return login form
            return self._create_login_form(event)

        # Inject user token into event for handler to use
        event.user_access_token = user_token_data.access_token
        return None

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

        # Extract timestamp from headers and add to payload
        # Note: verify_signature already validated that this header exists and is valid
        payload["timestamp"] = int(request.headers["X-Frameio-Request-Timestamp"])

        try:
            event = handler_reg.model.model_validate(payload)

            # Check user authentication if required
            if handler_reg.require_user_auth:
                # Only ActionEvent has user_id
                if not isinstance(event, ActionEvent):
                    return Response("User authentication only supported for action events.", status_code=400)

                # Check if user is authenticated
                login_form = await self._check_user_auth(event)
                if login_form:
                    return JSONResponse(login_form.model_dump(exclude_none=True))

            final_handler = cast(Callable[[AnyEvent], Awaitable[AnyResponse]], handler_reg.func)
            handler_with_middleware = self._build_middleware_chain(final_handler)
            response_data = await handler_with_middleware(event)

            if isinstance(response_data, Message) or isinstance(response_data, Form):
                return JSONResponse(response_data.model_dump(exclude_none=True))

            return Response("OK", status_code=200)

        except ValidationError as e:
            return Response(f"Payload validation error: {e}", status_code=422)
        except RuntimeError as e:
            # OAuth configuration errors
            return Response(str(e), status_code=500)
        except Exception as e:
            print(f"Error processing event '{event_type}': {e}")
            return Response("Internal Server Error", status_code=500)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """ASGI call interface to delegate to the underlying Starlette app."""
        await self._asgi_app(scope, receive, send)
