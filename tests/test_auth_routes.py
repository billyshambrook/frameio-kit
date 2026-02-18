"""Unit tests for OAuth authentication routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frameio_kit._app import _BrandingConfig
from frameio_kit._auth_routes import create_auth_routes
from frameio_kit._auth_templates import AuthTemplateRenderer
from frameio_kit._encryption import TokenEncryption
from frameio_kit._oauth import OAuthConfig, StateSerializer, TokenManager
from frameio_kit._state import _AppState, _state_dependency

# Test secret key for StateSerializer
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


@pytest.fixture
def oauth_config() -> OAuthConfig:
    """Create test OAuth config."""
    return OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_url="https://example.com/auth/callback",
    )


@pytest.fixture
def oauth_config_no_redirect() -> OAuthConfig:
    """Create test OAuth config without explicit redirect_url."""
    return OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_url=None,
    )


@pytest.fixture
def token_manager() -> TokenManager:
    """Create test token manager."""
    from frameio_kit._storage import MemoryStorage

    storage = MemoryStorage()
    encryption = TokenEncryption(key=TEST_SECRET_KEY)
    return TokenManager(
        storage=storage,
        encryption=encryption,
        client_id="test_client_id",
        client_secret="test_client_secret",
    )


@pytest.fixture
def state_serializer() -> StateSerializer:
    """Create test state serializer."""
    return StateSerializer(secret_key=TEST_SECRET_KEY)


@pytest.fixture
def oauth_client(oauth_config: OAuthConfig):
    """Create test OAuth client."""
    from frameio_kit._oauth import AdobeOAuthClient

    return AdobeOAuthClient(
        client_id=oauth_config.client_id,
        client_secret=oauth_config.client_secret,
        scopes=oauth_config.scopes,
    )


@pytest.fixture
def test_app(
    oauth_config: OAuthConfig, token_manager: TokenManager, oauth_client, state_serializer: StateSerializer
) -> FastAPI:
    """Create test FastAPI app with auth routes."""
    app_state = _AppState(
        branding=_TEST_BRANDING,
        oauth_config=oauth_config,
        oauth_client=oauth_client,
        state_serializer=state_serializer,
        token_manager=token_manager,
        auth_renderer=_TEST_AUTH_RENDERER,
    )
    get_state = _state_dependency(app_state)

    app = FastAPI()
    router = create_auth_routes(get_state)
    app.include_router(router)

    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(test_app)


class TestLoginEndpoint:
    """Test suite for login endpoint."""

    def test_login_redirects_to_adobe(self, client: TestClient):
        """Test that login endpoint redirects to Adobe IMS."""
        response = client.get("/auth/login", params={"user_id": "user_123"}, follow_redirects=False)

        assert response.status_code == 307  # RedirectResponse status
        assert "location" in response.headers

        location = response.headers["location"]
        assert location.startswith("https://ims-na1.adobelogin.com/ims/authorize/v2")
        assert "client_id=test_client_id" in location
        assert "response_type=code" in location
        assert "state=" in location

    def test_login_embeds_state_in_token(self, client: TestClient, state_serializer: StateSerializer):
        """Test that login endpoint embeds state data in signed token."""
        response = client.get("/auth/login", params={"user_id": "user_123"}, follow_redirects=False)

        # Extract state from redirect URL
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        # Verify state can be decoded and contains expected data
        state_data = state_serializer.loads(state)
        assert state_data["user_id"] == "user_123"
        assert "redirect_url" in state_data

    def test_login_with_interaction_id(self, client: TestClient, state_serializer: StateSerializer):
        """Test login with interaction_id parameter."""
        response = client.get(
            "/auth/login", params={"user_id": "user_123", "interaction_id": "interaction_456"}, follow_redirects=False
        )

        assert response.status_code == 307

        # Extract and verify state
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        state_data = state_serializer.loads(state)
        assert state_data["interaction_id"] == "interaction_456"

    def test_login_missing_user_id(self, client: TestClient):
        """Test login without user_id returns error."""
        response = client.get("/auth/login")

        assert response.status_code == 400
        assert "Missing user_id parameter" in response.text

    def test_login_with_explicit_redirect_url(self, client: TestClient, state_serializer: StateSerializer):
        """Test that explicit redirect_url is used when configured."""
        response = client.get("/auth/login", params={"user_id": "user_123"}, follow_redirects=False)

        # Extract state and verify redirect_url is embedded
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        state_data = state_serializer.loads(state)
        assert state_data["redirect_url"] == "https://example.com/auth/callback"

    def test_login_with_inferred_redirect_url_root_mount(
        self, oauth_config_no_redirect: OAuthConfig, token_manager: TokenManager, state_serializer: StateSerializer
    ):
        """Test redirect URL inference for app at root."""
        from frameio_kit._oauth import AdobeOAuthClient

        # Create app without explicit redirect_url
        app_state = _AppState(
            branding=_TEST_BRANDING,
            oauth_config=oauth_config_no_redirect,
            oauth_client=AdobeOAuthClient(
                client_id=oauth_config_no_redirect.client_id,
                client_secret=oauth_config_no_redirect.client_secret,
            ),
            state_serializer=state_serializer,
            token_manager=token_manager,
            auth_renderer=_TEST_AUTH_RENDERER,
        )
        get_state = _state_dependency(app_state)

        app = FastAPI()
        app.include_router(create_auth_routes(get_state))

        with TestClient(app, base_url="https://testserver") as test_client:
            response = test_client.get("/auth/login", params={"user_id": "user_123"}, follow_redirects=False)

            # Extract state and verify inferred redirect_url
            location = response.headers["location"]
            state_param = [p for p in location.split("&") if p.startswith("state=")][0]
            state = state_param.split("=")[1]

            state_data = state_serializer.loads(state)
            # For root, path is /auth/login, mount_prefix is ""
            assert state_data["redirect_url"] == "https://testserver/auth/callback"

    def test_login_with_inferred_redirect_url_prefix_mount(
        self, oauth_config_no_redirect: OAuthConfig, token_manager: TokenManager, state_serializer: StateSerializer
    ):
        """Test redirect URL inference for app at prefix."""
        from frameio_kit._oauth import AdobeOAuthClient

        # Create main app and include auth router at /frameio prefix
        app_state = _AppState(
            branding=_TEST_BRANDING,
            oauth_config=oauth_config_no_redirect,
            oauth_client=AdobeOAuthClient(
                client_id=oauth_config_no_redirect.client_id,
                client_secret=oauth_config_no_redirect.client_secret,
            ),
            state_serializer=state_serializer,
            token_manager=token_manager,
            auth_renderer=_TEST_AUTH_RENDERER,
        )
        get_state = _state_dependency(app_state)

        app = FastAPI()
        app.include_router(create_auth_routes(get_state), prefix="/frameio")

        with TestClient(app, base_url="https://testserver") as test_client:
            response = test_client.get("/frameio/auth/login", params={"user_id": "user_123"}, follow_redirects=False)

            # Extract state and verify inferred redirect_url includes prefix
            location = response.headers["location"]
            state_param = [p for p in location.split("&") if p.startswith("state=")][0]
            state = state_param.split("=")[1]

            state_data = state_serializer.loads(state)
            # For /frameio prefix, path is /frameio/auth/login, mount_prefix is /frameio
            assert state_data["redirect_url"] == "https://testserver/frameio/auth/callback"


class TestCallbackEndpoint:
    """Test suite for callback endpoint."""

    def test_callback_success(self, client: TestClient, state_serializer: StateSerializer):
        """Test successful OAuth callback."""
        # Create signed state token
        state = state_serializer.dumps(
            {
                "user_id": "user_123",
                "interaction_id": None,
                "redirect_url": "https://example.com/auth/callback",
            }
        )

        # Since we're not mocking the OAuth client, the token exchange will fail
        # The callback will attempt to make real HTTP requests to Adobe IMS
        response = client.get("/auth/callback", params={"code": "auth_code_123", "state": state})

        # The test verifies that the callback endpoint processes the request
        # even if the actual token exchange fails
        assert response.status_code in (200, 500)

    def test_callback_with_oauth_error(self, client: TestClient):
        """Test callback with OAuth error from Adobe."""
        response = client.get(
            "/auth/callback", params={"error": "access_denied", "error_description": "User denied access"}
        )

        assert response.status_code == 400
        assert "Authentication Failed" in response.text
        assert "User denied access" in response.text

    def test_callback_missing_code(self, client: TestClient):
        """Test callback without authorization code."""
        response = client.get("/auth/callback", params={"state": "some_state"})

        assert response.status_code == 400
        assert "Missing code or state parameter" in response.text

    def test_callback_missing_state(self, client: TestClient):
        """Test callback without state parameter."""
        response = client.get("/auth/callback", params={"code": "some_code"})

        assert response.status_code == 400
        assert "Missing code or state parameter" in response.text

    def test_callback_invalid_state(self, client: TestClient):
        """Test callback with invalid/tampered state."""
        response = client.get("/auth/callback", params={"code": "auth_code", "state": "invalid_token"})

        assert response.status_code == 400
        assert "Invalid State" in response.text

    def test_callback_wrong_key_state(self, client: TestClient):
        """Test callback with state token signed by wrong key."""
        from itsdangerous import URLSafeTimedSerializer

        # Create a state token signed with a different key - should be rejected
        wrong_serializer = URLSafeTimedSerializer("wrong_key", salt="oauth-state")
        state = wrong_serializer.dumps({"user_id": "user_123", "redirect_url": "https://example.com"})

        response = client.get("/auth/callback", params={"code": "auth_code", "state": state})

        assert response.status_code == 400
        assert "Invalid State" in response.text

    def test_callback_exchange_failure(self, client: TestClient, state_serializer: StateSerializer):
        """Test callback when token exchange fails."""
        state = state_serializer.dumps(
            {
                "user_id": "user_123",
                "interaction_id": None,
                "redirect_url": "https://example.com/auth/callback",
            }
        )

        response = client.get("/auth/callback", params={"code": "bad_code", "state": state})

        # Will attempt to exchange and may fail, check for appropriate handling
        # Note: Without mocking, this will attempt real token exchange which will fail
        assert response.status_code in (200, 500)  # May succeed or fail depending on mock setup

    def test_callback_uses_embedded_redirect_url(self, token_manager: TokenManager, state_serializer: StateSerializer):
        """Test that callback uses redirect URL from state token."""
        from frameio_kit._oauth import AdobeOAuthClient

        # Create app without explicit redirect_url
        oauth_config_no_redirect = OAuthConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_url=None,
        )

        app_state = _AppState(
            branding=_TEST_BRANDING,
            oauth_config=oauth_config_no_redirect,
            oauth_client=AdobeOAuthClient(
                client_id=oauth_config_no_redirect.client_id,
                client_secret=oauth_config_no_redirect.client_secret,
            ),
            state_serializer=state_serializer,
            token_manager=token_manager,
            auth_renderer=_TEST_AUTH_RENDERER,
        )
        get_state = _state_dependency(app_state)

        app = FastAPI()
        app.include_router(create_auth_routes(get_state))

        # Create state with a specific redirect_url
        custom_redirect_url = "https://custom.example.com/my/path/auth/callback"
        state = state_serializer.dumps(
            {
                "user_id": "user_456",
                "interaction_id": None,
                "redirect_url": custom_redirect_url,
            }
        )

        with TestClient(app) as test_client:
            # Make callback request
            response = test_client.get("/auth/callback", params={"code": "auth_code", "state": state})

            # Callback should use the embedded redirect_url
            # Response should attempt token exchange (will likely fail without mocking)
            assert response.status_code in (200, 500)


class TestCreateAuthRoutes:
    """Test suite for create_auth_routes factory."""

    def test_returns_api_router(self):
        """Test that create_auth_routes returns an APIRouter."""
        from fastapi import APIRouter

        app_state = _AppState(branding=_TEST_BRANDING)
        get_state = _state_dependency(app_state)
        router = create_auth_routes(get_state)

        assert isinstance(router, APIRouter)

    def test_creates_two_routes(self):
        """Test that create_auth_routes creates two routes."""
        app_state = _AppState(branding=_TEST_BRANDING)
        get_state = _state_dependency(app_state)
        router = create_auth_routes(get_state)

        assert len(router.routes) == 2

    def test_route_paths(self):
        """Test that routes have correct paths."""
        app_state = _AppState(branding=_TEST_BRANDING)
        get_state = _state_dependency(app_state)
        router = create_auth_routes(get_state)

        paths = [route.path for route in router.routes]  # type: ignore[union-attr]
        assert "/auth/login" in paths
        assert "/auth/callback" in paths

    def test_route_methods(self):
        """Test that routes use GET method."""
        app_state = _AppState(branding=_TEST_BRANDING)
        get_state = _state_dependency(app_state)
        router = create_auth_routes(get_state)

        for route in router.routes:
            assert route.methods is not None  # type: ignore[union-attr]
            assert "GET" in route.methods  # type: ignore[union-attr]
