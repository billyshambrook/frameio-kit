"""Unit tests for OAuth authentication routes."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from frameio_kit._auth_routes import create_auth_routes
from frameio_kit._encryption import TokenEncryption
from frameio_kit._oauth import AdobeOAuthClient, TokenData, TokenManager


@pytest.fixture
def oauth_client() -> AdobeOAuthClient:
    """Create test OAuth client."""
    return AdobeOAuthClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="https://example.com/auth/callback",
    )


@pytest.fixture
def token_manager() -> TokenManager:
    """Create test token manager."""
    from key_value.aio.stores.memory import MemoryStore

    storage = MemoryStore()
    encryption = TokenEncryption(key=TokenEncryption.generate_key())
    oauth_client = AdobeOAuthClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="https://example.com/auth/callback",
    )
    return TokenManager(storage=storage, encryption=encryption, oauth_client=oauth_client)


@pytest.fixture
def test_app(oauth_client: AdobeOAuthClient, token_manager: TokenManager) -> Starlette:
    """Create test Starlette app with auth routes."""
    app = Starlette()
    app.state.oauth_client = oauth_client
    app.state.token_manager = token_manager

    # Add auth routes
    auth_routes = create_auth_routes(token_manager, oauth_client)
    app.routes.extend(auth_routes)

    return app


@pytest.fixture
def client(test_app: Starlette) -> TestClient:
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

    async def test_login_stores_state(self, client: TestClient, token_manager: TokenManager):
        """Test that login endpoint stores CSRF state in storage."""
        response = client.get("/auth/login", params={"user_id": "user_123"}, follow_redirects=False)

        # Extract state from redirect URL
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        # Verify state is stored in storage backend
        state_key = f"oauth_state:{state}"
        state_data = await token_manager.storage.get(state_key)
        assert state_data is not None
        assert state_data["user_id"] == "user_123"

    async def test_login_with_interaction_id(self, client: TestClient, token_manager: TokenManager):
        """Test login with interaction_id parameter."""
        response = client.get(
            "/auth/login", params={"user_id": "user_123", "interaction_id": "interaction_456"}, follow_redirects=False
        )

        assert response.status_code == 307

        # Extract and verify state
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        state_key = f"oauth_state:{state}"
        state_data = await token_manager.storage.get(state_key)
        assert state_data is not None
        assert state_data["interaction_id"] == "interaction_456"

    def test_login_missing_user_id(self, client: TestClient):
        """Test login without user_id returns error."""
        response = client.get("/auth/login")

        assert response.status_code == 400
        assert "Missing user_id parameter" in response.text


class TestCallbackEndpoint:
    """Test suite for callback endpoint."""

    async def test_callback_success(self, client: TestClient, test_app: Starlette, token_manager: TokenManager):
        """Test successful OAuth callback."""
        # Set up state in storage
        state = "test_state_123"
        state_key = f"oauth_state:{state}"
        await token_manager.storage.put(
            state_key,
            {
                "user_id": "user_123",
                "interaction_id": None,
            },
            ttl=600,
        )

        # Mock token exchange
        mock_token_data = TokenData(
            access_token="new_access_token",
            refresh_token="new_refresh_token",
            expires_at=datetime.now() + timedelta(hours=24),
            scopes=["openid"],
            user_id="",
        )

        with patch.object(test_app.state.oauth_client, "exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = mock_token_data

            response = client.get("/auth/callback", params={"code": "auth_code_123", "state": state})

            assert response.status_code == 200
            assert "Authentication Successful" in response.text
            assert "window.close()" in response.text  # Auto-close script

            # Verify token was exchanged
            mock_exchange.assert_called_once_with("auth_code_123")

            # State should be consumed
            state_data = await token_manager.storage.get(state_key)
            assert state_data is None

    def test_callback_with_oauth_error(self, client: TestClient):
        """Test callback with OAuth error from Adobe."""
        response = client.get(
            "/auth/callback", params={"error": "access_denied", "error_description": "User denied access"}
        )

        assert response.status_code == 400
        assert "Authentication Failed" in response.text
        assert "access_denied" in response.text
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
        """Test callback with invalid/unknown state."""
        response = client.get("/auth/callback", params={"code": "auth_code", "state": "unknown_state"})

        assert response.status_code == 400
        assert "Invalid or Expired State" in response.text

    async def test_callback_exchange_failure(
        self, client: TestClient, test_app: Starlette, token_manager: TokenManager
    ):
        """Test callback when token exchange fails."""
        state = "test_state_123"
        state_key = f"oauth_state:{state}"
        await token_manager.storage.put(
            state_key,
            {
                "user_id": "user_123",
                "interaction_id": None,
            },
            ttl=600,
        )

        # Mock exchange to fail
        with patch.object(test_app.state.oauth_client, "exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.side_effect = Exception("Token exchange failed")

            response = client.get("/auth/callback", params={"code": "bad_code", "state": state})

            assert response.status_code == 500
            assert "Authentication Failed" in response.text
            # Error details should not be exposed to users for security
            assert "An unexpected error occurred" in response.text
            assert "Token exchange failed" not in response.text


class TestCreateAuthRoutes:
    """Test suite for create_auth_routes factory."""

    def test_creates_two_routes(self, oauth_client: AdobeOAuthClient, token_manager: TokenManager):
        """Test that create_auth_routes returns two routes."""
        routes = create_auth_routes(token_manager, oauth_client)

        assert len(routes) == 2

    def test_route_paths(self, oauth_client: AdobeOAuthClient, token_manager: TokenManager):
        """Test that routes have correct paths."""
        routes = create_auth_routes(token_manager, oauth_client)

        paths = [route.path for route in routes]
        assert "/auth/login" in paths
        assert "/auth/callback" in paths

    def test_route_methods(self, oauth_client: AdobeOAuthClient, token_manager: TokenManager):
        """Test that routes use GET method."""
        routes = create_auth_routes(token_manager, oauth_client)

        for route in routes:
            assert route.methods is not None
            assert "GET" in route.methods
