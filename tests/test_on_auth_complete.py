"""Tests for on_auth_complete callback in custom action OAuth flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import RedirectResponse

from frameio_kit._app import AuthCompleteContext, _BrandingConfig, _HandlerRegistration
from frameio_kit._auth_routes import create_auth_routes
from frameio_kit._auth_templates import AuthTemplateRenderer
from frameio_kit._encryption import TokenEncryption
from frameio_kit._events import ActionEvent
from frameio_kit._oauth import OAuthConfig, StateSerializer, TokenManager
from frameio_kit._storage import MemoryStorage

TEST_SECRET_KEY = TokenEncryption.generate_key()

_TEST_BRANDING = _BrandingConfig(
    name="Test App",
    description="",
    logo_url=None,
    primary_color="#6366f1",
    accent_color="#8b5cf6",
    custom_css=None,
    show_powered_by=True,
)
_TEST_AUTH_RENDERER = AuthTemplateRenderer(_TEST_BRANDING)

_ACTION_EVENT_DATA = {
    "type": "my_app.transcribe",
    "account_id": "acc_123",
    "action_id": "act_123",
    "interaction_id": "int_456",
    "project": {"id": "proj_123"},
    "resource": {"id": "file_123", "type": "file"},
    "user": {"id": "user_789"},
    "workspace": {"id": "ws_123"},
    "data": None,
    "timestamp": 1234567890,
}


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def token_manager(storage: MemoryStorage) -> TokenManager:
    encryption = TokenEncryption(key=TEST_SECRET_KEY)
    return TokenManager(
        storage=storage,
        encryption=encryption,
        client_id="test_client_id",
        client_secret="test_client_secret",
    )


@pytest.fixture
def state_serializer() -> StateSerializer:
    return StateSerializer(secret_key=TEST_SECRET_KEY)


@pytest.fixture
def oauth_client():
    from frameio_kit._oauth import AdobeOAuthClient

    return AdobeOAuthClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
    )


def _make_test_app(
    token_manager: TokenManager,
    state_serializer: StateSerializer,
    oauth_client,
    action_handlers: dict | None = None,
) -> Starlette:
    app = Starlette()
    app.state.oauth_config = OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_url="https://example.com/auth/callback",
    )
    app.state.token_manager = token_manager
    app.state.oauth_client = oauth_client
    app.state.state_serializer = state_serializer
    app.state.auth_renderer = _TEST_AUTH_RENDERER
    if action_handlers is not None:
        app.state._action_handlers = action_handlers
    auth_routes = create_auth_routes()
    app.routes.extend(auth_routes)
    return app


def _make_state(state_serializer: StateSerializer, action_type: str | None = None) -> str:
    return state_serializer.dumps(
        {
            "user_id": "user_789",
            "interaction_id": "int_456",
            "redirect_url": "https://example.com/auth/callback",
            "action_type": action_type,
        }
    )


class _MockTokenExchange:
    """Context manager that patches both exchange_code and store_token."""

    def __enter__(self):
        self._exchange_patch = patch(
            "frameio_kit._oauth.AdobeOAuthClient.exchange_code",
            new_callable=AsyncMock,
            return_value=MagicMock(),  # Return a mock TokenData-like object
        )
        self._store_patch = patch(
            "frameio_kit._oauth.TokenManager.store_token",
            new_callable=AsyncMock,
        )
        self._exchange_patch.__enter__()
        self._store_patch.__enter__()
        return self

    def __exit__(self, *args):
        self._store_patch.__exit__(*args)
        self._exchange_patch.__exit__(*args)


def _mock_token_exchange():
    return _MockTokenExchange()


def _make_mock_request() -> MagicMock:
    mock_request = MagicMock()
    mock_request.url = MagicMock()
    mock_request.url.scheme = "https"
    mock_request.url.hostname = "example.com"
    mock_request.url.port = None
    mock_request.headers = {}
    mock_request.scope = {"root_path": "", "path": "/"}
    mock_request.base_url = MagicMock()
    mock_request.base_url.__str__ = lambda self: "https://example.com/"
    return mock_request


class TestLoginEndpointActionType:
    """Test action_type flows through login URL and state token."""

    async def test_login_embeds_action_type_in_state(self, token_manager, state_serializer, oauth_client):
        """Test that action_type from query params is embedded in the state token."""
        app = _make_test_app(token_manager, state_serializer, oauth_client)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            response = await client.get(
                "/auth/login",
                params={"user_id": "user_789", "interaction_id": "int_456", "action_type": "my_app.transcribe"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        state_data = state_serializer.loads(state)
        assert state_data["action_type"] == "my_app.transcribe"

    async def test_login_without_action_type(self, token_manager, state_serializer, oauth_client):
        """Test that missing action_type results in None in state."""
        app = _make_test_app(token_manager, state_serializer, oauth_client)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            response = await client.get(
                "/auth/login",
                params={"user_id": "user_789"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        state_data = state_serializer.loads(state)
        assert state_data["action_type"] is None


class TestCallbackOnAuthComplete:
    """Test on_auth_complete callback behavior in the callback endpoint."""

    async def test_callback_invokes_on_auth_complete_with_redirect(
        self, storage, token_manager, state_serializer, oauth_client
    ):
        """Test callback returns custom Response from on_auth_complete."""
        callback = AsyncMock(return_value=RedirectResponse("https://myapp.com/setup"))
        handler_reg = _HandlerRegistration(
            func=AsyncMock(),
            name="Transcribe",
            description="Transcribe file",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=callback,
        )
        action_handlers = {"my_app.transcribe": handler_reg}

        app = _make_test_app(token_manager, state_serializer, oauth_client, action_handlers)

        await storage.put("pending_auth:user_789:int_456", _ACTION_EVENT_DATA, ttl=600)

        state = _make_state(state_serializer, action_type="my_app.transcribe")

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get(
                    "/auth/callback",
                    params={"code": "auth_code", "state": state},
                    follow_redirects=False,
                )

        assert response.status_code == 307
        assert response.headers["location"] == "https://myapp.com/setup"

        # Verify callback was called with AuthCompleteContext
        callback.assert_called_once()
        ctx = callback.call_args[0][0]
        assert isinstance(ctx, AuthCompleteContext)
        assert ctx.event.type == "my_app.transcribe"
        assert ctx.event.user_id == "user_789"
        assert ctx.event.resource_id == "file_123"

    async def test_callback_returns_none_falls_through_to_success(
        self, storage, token_manager, state_serializer, oauth_client
    ):
        """Test callback returning None shows default success page."""
        callback = AsyncMock(return_value=None)
        handler_reg = _HandlerRegistration(
            func=AsyncMock(),
            name="Transcribe",
            description="Transcribe file",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=callback,
        )
        action_handlers = {"my_app.transcribe": handler_reg}

        app = _make_test_app(token_manager, state_serializer, oauth_client, action_handlers)

        await storage.put("pending_auth:user_789:int_456", _ACTION_EVENT_DATA, ttl=600)

        state = _make_state(state_serializer, action_type="my_app.transcribe")

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/auth/callback", params={"code": "auth_code", "state": state})

        assert response.status_code == 200
        callback.assert_called_once()

    async def test_callback_exception_falls_through_to_success(
        self, storage, token_manager, state_serializer, oauth_client
    ):
        """Test callback raising exception falls through to default success page."""
        callback = AsyncMock(side_effect=RuntimeError("callback failed"))
        handler_reg = _HandlerRegistration(
            func=AsyncMock(),
            name="Transcribe",
            description="Transcribe file",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=callback,
        )
        action_handlers = {"my_app.transcribe": handler_reg}

        app = _make_test_app(token_manager, state_serializer, oauth_client, action_handlers)

        await storage.put("pending_auth:user_789:int_456", _ACTION_EVENT_DATA, ttl=600)

        state = _make_state(state_serializer, action_type="my_app.transcribe")

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/auth/callback", params={"code": "auth_code", "state": state})

        # Should not fail — falls through to success page
        assert response.status_code == 200

    async def test_expired_stored_event_falls_through(self, storage, token_manager, state_serializer, oauth_client):
        """Test that missing/expired stored event falls through to success page."""
        callback = AsyncMock(return_value=RedirectResponse("https://myapp.com/setup"))
        handler_reg = _HandlerRegistration(
            func=AsyncMock(),
            name="Transcribe",
            description="Transcribe file",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=callback,
        )
        action_handlers = {"my_app.transcribe": handler_reg}

        app = _make_test_app(token_manager, state_serializer, oauth_client, action_handlers)

        # Deliberately NOT storing the event in storage
        state = _make_state(state_serializer, action_type="my_app.transcribe")

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/auth/callback", params={"code": "auth_code", "state": state})

        # Should fall through to success page
        assert response.status_code == 200
        # Callback should NOT have been called (no event data)
        callback.assert_not_called()

    async def test_stored_event_cleaned_up_after_callback(self, storage, token_manager, state_serializer, oauth_client):
        """Test stored event is deleted after callback invocation."""
        callback = AsyncMock(return_value=None)
        handler_reg = _HandlerRegistration(
            func=AsyncMock(),
            name="Transcribe",
            description="Transcribe file",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=callback,
        )
        action_handlers = {"my_app.transcribe": handler_reg}

        app = _make_test_app(token_manager, state_serializer, oauth_client, action_handlers)

        await storage.put("pending_auth:user_789:int_456", _ACTION_EVENT_DATA, ttl=600)

        state = _make_state(state_serializer, action_type="my_app.transcribe")

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                await client.get("/auth/callback", params={"code": "auth_code", "state": state})

        # Verify cleanup
        result = await storage.get("pending_auth:user_789:int_456")
        assert result is None

    async def test_no_action_type_renders_default_success(self, token_manager, state_serializer, oauth_client):
        """Test no action_type in state renders default success page."""
        app = _make_test_app(token_manager, state_serializer, oauth_client)

        state = _make_state(state_serializer, action_type=None)

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/auth/callback", params={"code": "auth_code", "state": state})

        assert response.status_code == 200

    async def test_no_on_auth_complete_handler_renders_default_success(
        self, token_manager, state_serializer, oauth_client
    ):
        """Test action_type present but handler has no on_auth_complete."""
        handler_reg = _HandlerRegistration(
            func=AsyncMock(),
            name="Analyze",
            description="Analyze file",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=None,
        )
        action_handlers = {"my_app.analyze": handler_reg}

        app = _make_test_app(token_manager, state_serializer, oauth_client, action_handlers)

        state = _make_state(state_serializer, action_type="my_app.analyze")

        with _mock_token_exchange():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/auth/callback", params={"code": "auth_code", "state": state})

        assert response.status_code == 200


class TestCreateLoginFormEventStorage:
    """Test event storage in _create_login_form."""

    @pytest.fixture
    def app_with_oauth(self, storage):
        """Create an App with OAuth configured."""
        from frameio_kit import App, OAuthConfig

        return App(
            oauth=OAuthConfig(client_id="cid", client_secret="csecret"),
            storage=storage,
        )

    async def test_event_stored_when_on_auth_complete_set(self, app_with_oauth, storage):
        """Test event is stored in storage when on_auth_complete is set."""
        callback = AsyncMock(return_value=None)

        @app_with_oauth.on_action(
            "my_app.transcribe",
            name="Transcribe",
            description="Transcribe file",
            secret="test_secret",
            require_user_auth=True,
            on_auth_complete=callback,
        )
        async def handler(event: ActionEvent):
            pass

        event = ActionEvent.model_validate(_ACTION_EVENT_DATA)
        mock_request = _make_mock_request()

        await app_with_oauth._create_login_form(event, mock_request)

        # Verify event was stored
        stored = await storage.get("pending_auth:user_789:int_456")
        assert stored is not None
        assert stored["type"] == "my_app.transcribe"
        assert stored["user"]["id"] == "user_789"

    async def test_event_not_stored_when_no_on_auth_complete(self, app_with_oauth, storage):
        """Test event is NOT stored when on_auth_complete is not set."""

        @app_with_oauth.on_action(
            "my_app.analyze",
            name="Analyze",
            description="Analyze file",
            secret="test_secret",
            require_user_auth=True,
        )
        async def handler(event: ActionEvent):
            pass

        event = ActionEvent.model_validate(_ACTION_EVENT_DATA | {"type": "my_app.analyze"})
        mock_request = _make_mock_request()

        await app_with_oauth._create_login_form(event, mock_request)

        # Verify event was NOT stored
        stored = await storage.get("pending_auth:user_789:int_456")
        assert stored is None

    async def test_login_url_contains_action_type(self, app_with_oauth, storage):
        """Test that the login URL includes action_type parameter."""

        @app_with_oauth.on_action(
            "my_app.transcribe",
            name="Transcribe",
            description="Transcribe file",
            secret="test_secret",
            require_user_auth=True,
        )
        async def handler(event: ActionEvent):
            pass

        event = ActionEvent.model_validate(_ACTION_EVENT_DATA)
        mock_request = _make_mock_request()

        form = await app_with_oauth._create_login_form(event, mock_request)

        # The form should have a link field with the login URL containing action_type
        login_url = form.fields[0].value
        assert "action_type=my_app.transcribe" in login_url


class TestValidateConfiguration:
    """Test validate_configuration catches on_auth_complete misconfigurations."""

    def test_on_auth_complete_without_require_user_auth(self):
        """Test that on_auth_complete without require_user_auth is caught."""
        from frameio_kit import App

        app = App()

        callback = AsyncMock(return_value=None)

        # Manually register to bypass decorator secret resolution
        app._action_handlers["my_app.test"] = _HandlerRegistration(
            func=AsyncMock(),
            name="Test",
            description="Test action",
            model=ActionEvent,
            require_user_auth=False,
            on_auth_complete=callback,
        )

        errors = app.validate_configuration()
        assert len(errors) == 1
        assert "on_auth_complete" in errors[0]
        assert "require_user_auth is False" in errors[0]

    def test_on_auth_complete_with_require_user_auth_is_valid(self):
        """Test that on_auth_complete with require_user_auth passes validation."""
        from frameio_kit import App, OAuthConfig

        app = App(oauth=OAuthConfig(client_id="cid", client_secret="csecret"))

        callback = AsyncMock(return_value=None)

        app._action_handlers["my_app.test"] = _HandlerRegistration(
            func=AsyncMock(),
            name="Test",
            description="Test action",
            model=ActionEvent,
            require_user_auth=True,
            on_auth_complete=callback,
        )

        errors = app.validate_configuration()
        assert len(errors) == 0
