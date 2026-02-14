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
    from frameio_kit import App, WebhookEvent, Message

    # Initialize the app, optionally with a token for API calls
    app = App(token=os.getenv("FRAMEIO_TOKEN"))

    # WEBHOOK_SECRET env var will be used automatically
    @app.on_webhook("file.ready")
    async def on_file_ready(event: WebhookEvent):
        print(f"File '{event.resource_id}' is now ready!")

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)
    ```
"""

import functools
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Awaitable, Callable, cast

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from ._auth_routes import create_auth_routes
from ._client import Client
from ._context import _user_token_context
from ._events import ActionEvent, AnyEvent, WebhookEvent
from ._exceptions import (
    ConfigurationError,
    EventValidationError,
    SecretResolutionError,
    SignatureVerificationError,
)
from ._middleware import Middleware
from ._oauth import OAuthConfig, TokenManager, infer_oauth_url
from ._oauth_manager import OAuthManager
from ._request_handler import RequestHandler, parse_request
from ._responses import AnyResponse, Form, Message
from ._secret_resolver import (
    ActionSecretResolver,
    SecretResolverProtocol,
    SecretResolutionStrategy,
    WebhookSecretResolver,
    resolve_secret_at_decorator_time,
)
from ._storage import Storage

logger = logging.getLogger(__name__)

# A handler for a standard webhook, which is non-interactive.
# It can only return a Message or nothing.
WebhookHandlerFunc = Callable[[WebhookEvent], Awaitable[None]]

# A handler for a custom action, which is interactive.
# It can return a Message, a Form for further input, or nothing.
ActionHandlerFunc = Callable[[ActionEvent], Awaitable[AnyResponse]]


@dataclass(frozen=True)
class _BrandingConfig:
    """Internal branding configuration shared between install UI and auth pages."""

    name: str
    description: str
    logo_url: str | None
    primary_color: str
    accent_color: str
    custom_css: str | None
    show_powered_by: bool


@dataclass
class _HandlerRegistration:
    """Stores metadata for a registered webhook or action handler."""

    func: WebhookHandlerFunc | ActionHandlerFunc
    secret: str | None = None
    secret_resolver: WebhookSecretResolver | ActionSecretResolver | None = None
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
        self,
        *,
        # API access
        token: str | None = None,
        api_url: str | None = None,
        middleware: list[Middleware] | None = None,
        # OAuth credentials
        oauth: OAuthConfig | None = None,
        # Shared infrastructure (used by both OAuth token storage and install records)
        storage: Storage | None = None,
        encryption_key: str | None = None,
        # Install system
        install: bool = False,
        install_session_ttl: int = 1800,
        base_url: str | None = None,
        # Branding (used by both install UI and auth callback pages)
        name: str | None = None,
        description: str = "",
        logo_url: str | None = None,
        primary_color: str = "#6366f1",
        accent_color: str = "#8b5cf6",
        custom_css: str | None = None,
        show_powered_by: bool = True,
    ) -> None:
        """Initializes the App.

        Args:
            token: An optional access token obtained from the Adobe Developer
                Console. If provided, this token will be used to authenticate
                API calls made via the ``app.client`` property.
            api_url: Optional base URL for the Frame.io API. Defaults to
                ``https://api.frame.io``. Override this for testing or to
                target a different API environment.
            middleware: An optional list of middleware classes to process
                requests before they reach the handler.
            oauth: Optional OAuth configuration for user authentication. When
                provided, enables Adobe Login OAuth flow for actions that
                require user-specific authentication.
            storage: Storage backend instance for persisting encrypted tokens
                and install records. If None, defaults to MemoryStorage.
            encryption_key: Optional encryption key for token storage. If None,
                uses FRAMEIO_AUTH_ENCRYPTION_KEY env var or generates ephemeral key.
            install: Whether to enable the self-service ``/install`` page.
                Requires ``oauth`` to also be configured.
            install_session_ttl: Install session TTL in seconds. Defaults to
                30 minutes (1800).
            base_url: Explicit public URL for the app. If not set, the URL is
                inferred from incoming requests.
            name: Display name shown in the install and auth UI headers.
                Defaults to ``"Authentication"`` when None.
            description: Description shown on the landing page.
            logo_url: URL to the partner logo image.
            primary_color: Hex color code for primary branding.
            accent_color: Hex color code for accent/secondary highlights.
            custom_css: Raw CSS string injected into page templates.
            show_powered_by: Whether to show "Powered by frameio-kit" footer.
        """
        self._token = token
        self._api_url = api_url
        self._middleware = middleware or []
        self._oauth_config = oauth
        self._storage = storage
        self._encryption_key = encryption_key
        self._install_enabled = install
        self._install_session_ttl = install_session_ttl
        self._base_url = base_url
        self._api_client: Client | None = None
        self._webhook_handlers: dict[str, _HandlerRegistration] = {}
        self._action_handlers: dict[str, _HandlerRegistration] = {}

        # Build branding config
        self._branding = _BrandingConfig(
            name=name if name is not None else "Authentication",
            description=description,
            logo_url=logo_url,
            primary_color=primary_color,
            accent_color=accent_color,
            custom_css=custom_css,
            show_powered_by=show_powered_by,
        )

        # Validate install requires oauth
        if self._install_enabled and not self._oauth_config:
            raise ConfigurationError("Installation system requires OAuth to be configured.")

        # Initialize OAuth manager if configured
        self._oauth_manager: OAuthManager | None = None
        if self._oauth_config:
            self._oauth_manager = OAuthManager(
                self._oauth_config,
                storage=self._storage,
                encryption_key=self._encryption_key,
            )

        # Initialize install components if configured
        self._install_manager = None
        self._install_secret_resolver = None
        self._secret_resolver: SecretResolverProtocol | None = None
        self._template_renderer = None
        if self._install_enabled and self._oauth_manager and self._oauth_config:
            from ._encryption import TokenEncryption
            from ._install_manager import InstallationManager
            from ._install_secret_resolver import InstallationSecretResolver
            from ._install_templates import TemplateRenderer
            from ._storage import MemoryStorage

            resolved_storage = self._storage if self._storage else MemoryStorage()
            encryption = TokenEncryption(key=self._encryption_key)

            self._install_manager = InstallationManager(
                storage=resolved_storage,
                encryption=encryption,
                app_name=self._branding.name,
                base_url=self._api_url,
            )
            self._template_renderer = TemplateRenderer(branding=self._branding)

            # Auto-wire secret resolver
            self._install_secret_resolver = InstallationSecretResolver(self._install_manager)
            self._secret_resolver = self._install_secret_resolver

        # Request handler for parsing and validation
        self._request_handler = RequestHandler()

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
            RuntimeError: If the `App` was initialized without a `token`.
        """
        if not self._token:
            raise RuntimeError("Cannot access API client. `token` was not provided to App.")
        if self._api_client is None:
            self._api_client = Client(token=self._token, base_url=self._api_url)
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
        if not self._oauth_manager:
            raise RuntimeError("Cannot access token manager. OAuth not configured in App initialization.")
        return self._oauth_manager.token_manager

    def validate_configuration(self) -> list[str]:
        """Check configuration is valid before accepting requests.

        This method validates that all registered handlers have valid
        configurations and that OAuth is properly set up for handlers
        that require user authentication.

        Returns:
            List of configuration error messages. Empty list if valid.

        Example:
            ```python
            errors = app.validate_configuration()
            if errors:
                for error in errors:
                    print(f"Configuration error: {error}")
                sys.exit(1)
            ```
        """
        errors: list[str] = []

        for event_type, reg in self._action_handlers.items():
            if reg.require_user_auth and not self._oauth_manager:
                errors.append(f"Action '{event_type}' requires user auth but OAuth not configured")

        return errors

    def on_webhook(self, event_type: str | list[str], secret: str | WebhookSecretResolver | None = None):
        """Decorator to register a function as a webhook event handler.

        This decorator registers an asynchronous function to be called whenever
        Frame.io sends a webhook event of the specified type(s). A webhook
        handler receives a `WebhookEvent` and must return `None`.

        Example:
            ```python
            from frameio_kit import App, WebhookEvent

            app = App()

            # Using explicit secret string
            @app.on_webhook(event_type="file.ready", secret="your-secret")
            async def on_file_ready(event: WebhookEvent):
                pass

            # Using decorator-level resolver
            async def resolve_secret(event: WebhookEvent) -> str:
                return await db.get_secret(event.account_id)

            @app.on_webhook(event_type="file.ready", secret=resolve_secret)
            async def on_file_ready(event: WebhookEvent):
                pass

            # Using WEBHOOK_SECRET environment variable
            @app.on_webhook(event_type="file.ready")
            async def on_another_event(event: WebhookEvent):
                pass
            ```

        Args:
            event_type: The Frame.io event type to listen for (e.g.,
                `"file.ready"`). You can also provide a list of strings to
                register the same handler for multiple event types.
            secret: The signing secret or a resolver function. Can be:
                - A string: Static secret for signature verification
                - A callable: Async function receiving WebhookEvent and returning secret
                - None: Falls back to app-level resolver or WEBHOOK_SECRET env var

        Raises:
            ValueError: If no secret source is available (no explicit secret,
                no app-level resolver, and no WEBHOOK_SECRET environment variable).
        """

        def decorator(func: WebhookHandlerFunc):
            static_secret, resolver = resolve_secret_at_decorator_time(
                secret, "WEBHOOK_SECRET", "Webhook", self._secret_resolver
            )

            events = [event_type] if isinstance(event_type, str) else event_type
            for event in events:
                self._webhook_handlers[event] = _HandlerRegistration(
                    func=func, secret=static_secret, secret_resolver=resolver, model=WebhookEvent
                )
            return func

        return decorator

    def on_action(
        self,
        event_type: str,
        *,
        name: str,
        description: str,
        secret: str | ActionSecretResolver | None = None,
        require_user_auth: bool = False,
    ):
        """Decorator to register a function as a custom action handler.

        This decorator connects an asynchronous function to a Custom Action in the
        Frame.io UI. The handler receives an `ActionEvent` and can return a
        `Message`, a `Form` for more input, or `None`.

        Example:
            ```python
            from frameio_kit import App, ActionEvent

            app = App()

            # Using explicit secret string
            @app.on_action("my_app.transcribe", name="Transcribe", description="Transcribe file", secret="your-secret")
            async def on_transcribe(event: ActionEvent):
                pass

            # Using decorator-level resolver
            async def resolve_secret(event: ActionEvent) -> str:
                return await db.get_secret(event.resource.id)

            @app.on_action("my_app.convert", name="Convert", description="Convert file", secret=resolve_secret)
            async def on_convert(event: ActionEvent):
                pass

            # Using CUSTOM_ACTION_SECRET environment variable
            @app.on_action("my_app.process", name="Process", description="Process file")
            async def on_process(event: ActionEvent):
                pass
            ```

        Args:
            event_type: A unique string you define to identify this action
                (e.g., `"my_app.transcribe"`). This is the `type` that will be
                present in the incoming payload.
            name: The user-visible name for the action in the Frame.io UI menu.
            description: A short, user-visible description of what the action does.
            secret: The signing secret or a resolver function. Can be:
                - A string: Static secret for signature verification
                - A callable: Async function receiving ActionEvent and returning secret
                - None: Falls back to app-level resolver or CUSTOM_ACTION_SECRET env var
            require_user_auth: If True, requires user to authenticate via Adobe
                Login OAuth before executing the handler. OAuth must be configured
                in App initialization for this to work.

        Raises:
            ValueError: If no secret source is available (no explicit secret,
                no app-level resolver, and no CUSTOM_ACTION_SECRET environment variable).
        """

        def decorator(func: ActionHandlerFunc):
            static_secret, resolver = resolve_secret_at_decorator_time(
                secret, "CUSTOM_ACTION_SECRET", "Custom action", self._secret_resolver
            )

            self._action_handlers[event_type] = _HandlerRegistration(
                func=func,
                secret=static_secret,
                secret_resolver=resolver,
                name=name,
                description=description,
                model=ActionEvent,
                require_user_auth=require_user_auth,
            )
            return func

        return decorator

    async def close(self) -> None:
        """Close underlying HTTP clients and release resources.

        Call this when shutting down the application to cleanly close
        connections. When running standalone with uvicorn this is handled
        automatically via the ASGI lifespan. When mounting inside another
        framework (e.g. FastAPI) you should call this from the parent
        app's lifespan shutdown.

        Example:
            ```python
            from contextlib import asynccontextmanager
            from fastapi import FastAPI

            @asynccontextmanager
            async def lifespan(app):
                yield
                await frameio_app.close()

            app = FastAPI(lifespan=lifespan)
            app.mount("/", frameio_app)
            ```
        """
        if self._api_client:
            try:
                await self._api_client.close()
            except Exception:
                logger.exception("Error closing API client")

        if self._oauth_manager:
            try:
                await self._oauth_manager.close()
            except Exception:
                logger.exception("Error closing OAuth manager")

    @asynccontextmanager
    async def _lifespan(self, app: Starlette):
        """ASGI lifespan handler for standalone usage."""
        yield
        await self.close()

    def _create_asgi_app(self) -> Starlette:
        """Builds the Starlette ASGI application with routes and lifecycle hooks."""
        routes = [Route("/", self._handle_request, methods=["POST"])]

        # Add OAuth routes if configured
        if self._oauth_manager:
            auth_routes = create_auth_routes()
            routes.extend(auth_routes)

        # Add install routes if configured
        if self._install_enabled:
            from ._install_routes import create_install_routes

            install_routes = create_install_routes()
            routes.extend(install_routes)

        starlette_app = Starlette(
            debug=False,
            routes=routes,
            lifespan=self._lifespan,
        )

        # Set state eagerly so it's available even when mounted as a
        # sub-application (where the inner lifespan may not run).
        starlette_app.state.branding = self._branding

        if self._oauth_manager and self._oauth_config:
            starlette_app.state.token_manager = self._oauth_manager.token_manager
            starlette_app.state.oauth_config = self._oauth_config
            starlette_app.state.oauth_client = self._oauth_manager.oauth_client
            starlette_app.state.state_serializer = self._oauth_manager.state_serializer

            # Set up auth template renderer for OAuth callback pages
            from ._auth_templates import AuthTemplateRenderer

            starlette_app.state.auth_renderer = AuthTemplateRenderer(self._branding)

        if self._install_enabled and self._install_manager and self._template_renderer:
            starlette_app.state.install_manager = self._install_manager
            starlette_app.state.install_session_ttl = self._install_session_ttl
            starlette_app.state.base_url = self._base_url
            starlette_app.state.template_renderer = self._template_renderer
            # Store references so the manifest can be built lazily (handlers
            # are registered via decorators after __init__ completes).
            starlette_app.state._webhook_handlers = self._webhook_handlers
            starlette_app.state._action_handlers = self._action_handlers

        return starlette_app

    def _find_handler(self, event_type: str) -> _HandlerRegistration | None:
        """Finds the registered handler for a given event type."""
        return self._webhook_handlers.get(event_type) or self._action_handlers.get(event_type)

    def _create_login_form(self, event: ActionEvent, request: Request) -> Form:
        """Create a Form prompting the user to authenticate.

        Args:
            event: The ActionEvent that triggered the auth request.
            request: The incoming request (used to infer login URL).

        Returns:
            A Form with a link to initiate the OAuth flow.
        """
        from ._responses import LinkField

        # Build login URL with user context
        if self._oauth_config is None:
            raise RuntimeError("OAuth config must be set to create login form")

        # Infer login URL from request (handles mount prefix correctly)
        login_url_base = infer_oauth_url(request, "/auth/login")
        login_url = f"{login_url_base}?user_id={event.user_id}"

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

    async def _check_user_auth(self, event: ActionEvent, request: Request) -> Form | None:
        """Check if user is authenticated and return login form if not.

        Args:
            event: The ActionEvent to check authentication for.
            request: The incoming request (used to infer login URL if needed).

        Returns:
            Login Form if user needs to authenticate, None if authenticated.

        Raises:
            ConfigurationError: If OAuth not configured but auth required.
        """
        if not self._oauth_manager:
            raise ConfigurationError("User authentication required but OAuth not configured.")

        # Check if user has a valid token
        user_token_data = await self._oauth_manager.token_manager.get_token(event.user_id)
        if not user_token_data:
            # User not authenticated - return login form
            return self._create_login_form(event, request)

        # Set user token in request context (not on event to prevent accidental logging)
        _user_token_context.set(user_token_data.access_token)
        return None

    async def _resolve_secret(self, handler_reg: _HandlerRegistration, event: WebhookEvent | ActionEvent) -> str:
        """Resolve the secret for signature verification.

        Args:
            handler_reg: The handler registration with secret configuration.
            event: The parsed event.

        Returns:
            The resolved secret string.

        Raises:
            SecretResolutionError: If secret resolution fails.
        """
        strategy = SecretResolutionStrategy(
            static_secret=handler_reg.secret,
            decorator_resolver=handler_reg.secret_resolver,
            app_resolver=self._secret_resolver,
        )
        return await strategy.resolve(event)

    async def _handle_request(self, request: Request) -> Response:
        """The main ASGI request handler."""
        body = await request.body()

        # Parse request
        try:
            parsed = parse_request(body, request.headers)
        except ValueError as e:
            return Response(str(e), status_code=400)

        event_type = parsed.event_type

        # Find handler
        handler_reg = self._find_handler(event_type)
        if not handler_reg:
            return Response(f"No handler registered for event type '{event_type}'.", status_code=404)

        # Validate event
        try:
            event = self._request_handler.validate(parsed.payload, handler_reg.model)
        except EventValidationError as e:
            logger.warning("Event validation failed: %s", e)
            return Response("Payload validation error.", status_code=422)

        # Resolve secret
        try:
            resolved_secret = await self._resolve_secret(handler_reg, event)
        except SecretResolutionError as e:
            logger.error("Secret resolution failed for event '%s': %s", event_type, e)
            return Response("Configuration error.", status_code=503)

        # Verify signature
        try:
            await self._request_handler.verify(request.headers, body, resolved_secret)
        except SignatureVerificationError:
            return Response("Invalid signature.", status_code=401)

        # Process event
        try:
            # Check user authentication if required
            if handler_reg.require_user_auth:
                # Only ActionEvent has user_id
                if not isinstance(event, ActionEvent):
                    return Response("User authentication only supported for action events.", status_code=400)

                # Check if user is authenticated
                login_form = await self._check_user_auth(event, request)
                if login_form:
                    return JSONResponse(login_form.model_dump(exclude_none=True))

            final_handler = cast(Callable[[AnyEvent], Awaitable[AnyResponse]], handler_reg.func)
            handler_with_middleware = self._build_middleware_chain(final_handler)
            response_data = await handler_with_middleware(event)

            # Webhook handlers are fire-and-forget; ignore any return value.
            is_webhook = event_type in self._webhook_handlers
            if not is_webhook and isinstance(response_data, (Message, Form)):
                return JSONResponse(response_data.model_dump(exclude_none=True))

            return Response("OK", status_code=200)

        except ConfigurationError as e:
            logger.error("Configuration error processing event '%s': %s", event_type, e)
            return Response("Configuration error.", status_code=503)
        except Exception:
            logger.exception("Error processing event '%s'", event_type)
            return Response("Internal Server Error", status_code=500)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """ASGI call interface to delegate to the underlying Starlette app."""
        await self._asgi_app(scope, receive, send)
