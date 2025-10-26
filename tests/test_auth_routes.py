"""Unit tests for OAuth authentication routes."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from frameio_kit._auth_routes import _oauth_states, create_auth_routes
from frameio_kit._encryption import TokenEncryption
from frameio_kit._oauth import AdobeOAuthClient, TokenManager
from frameio_kit._storage import TokenData


@pytest.fixture
def oauth_client() -> AdobeOAuthClient:
    """Create test OAuth client."""
    return AdobeOAuthClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="https://example.com/.auth/callback",
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
        redirect_uri="https://example.com/.auth/callback",
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


@pytest.fixture(autouse=True)
def clear_oauth_states():
    """Clear OAuth states before each test."""
    _oauth_states.clear()
    yield
    _oauth_states.clear()


class TestLoginEndpoint:
    """Test suite for login endpoint."""

    def test_login_redirects_to_adobe(self, client: TestClient):
        """Test that login endpoint redirects to Adobe IMS."""
        response = client.get("/.auth/login", params={"user_id": "user_123"}, follow_redirects=False)

        assert response.status_code == 307  # RedirectResponse status
        assert "location" in response.headers

        location = response.headers["location"]
        assert location.startswith("https://ims-na1.adobelogin.com/ims/authorize/v2")
        assert "client_id=test_client_id" in location
        assert "response_type=code" in location
        assert "state=" in location

    def test_login_stores_state(self, client: TestClient):
        """Test that login endpoint stores CSRF state."""
        response = client.get("/.auth/login", params={"user_id": "user_123"}, follow_redirects=False)

        # Extract state from redirect URL
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        # Verify state is stored
        assert state in _oauth_states
        assert _oauth_states[state]["user_id"] == "user_123"
        assert "created_at" in _oauth_states[state]

    def test_login_with_interaction_id(self, client: TestClient):
        """Test login with interaction_id parameter."""
        response = client.get(
            "/.auth/login", params={"user_id": "user_123", "interaction_id": "interaction_456"}, follow_redirects=False
        )

        assert response.status_code == 307

        # Extract and verify state
        location = response.headers["location"]
        state_param = [p for p in location.split("&") if p.startswith("state=")][0]
        state = state_param.split("=")[1]

        assert _oauth_states[state]["interaction_id"] == "interaction_456"

    def test_login_missing_user_id(self, client: TestClient):
        """Test login without user_id returns error."""
        response = client.get("/.auth/login")

        assert response.status_code == 400
        assert "Missing user_id parameter" in response.text

    def test_login_cleans_expired_states(self, client: TestClient):
        """Test that login cleans up expired states."""
        # Add an expired state
        _oauth_states["expired_state"] = {
            "user_id": "old_user",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=15),
        }

        # Add a valid state
        _oauth_states["valid_state"] = {
            "user_id": "current_user",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=5),
        }

        assert len(_oauth_states) == 2

        # Trigger login (which should clean up)
        client.get("/.auth/login", params={"user_id": "new_user"}, follow_redirects=False)

        # Expired state should be gone
        assert "expired_state" not in _oauth_states
        assert "valid_state" in _oauth_states


class TestCallbackEndpoint:
    """Test suite for callback endpoint."""

    async def test_callback_success(self, client: TestClient, test_app: Starlette):
        """Test successful OAuth callback."""
        # Set up state
        state = "test_state_123"
        _oauth_states[state] = {
            "user_id": "user_123",
            "interaction_id": None,
            "created_at": datetime.now(),
        }

        # Mock token exchange
        mock_token_data = TokenData(
            access_token="new_access_token",
            refresh_token="new_refresh_token",
            expires_at=datetime.now() + timedelta(hours=24),
            scopes=["openid"],
            user_id="",
        )

        with patch.object(
            test_app.state.oauth_client, "exchange_code", new_callable=AsyncMock
        ) as mock_exchange:
            mock_exchange.return_value = mock_token_data

            response = client.get("/.auth/callback", params={"code": "auth_code_123", "state": state})

            assert response.status_code == 200
            assert "Authentication Successful" in response.text
            assert "window.close()" in response.text  # Auto-close script

            # Verify token was exchanged
            mock_exchange.assert_called_once_with("auth_code_123")

            # State should be consumed
            assert state not in _oauth_states

    def test_callback_with_oauth_error(self, client: TestClient):
        """Test callback with OAuth error from Adobe."""
        response = client.get(
            "/.auth/callback", params={"error": "access_denied", "error_description": "User denied access"}
        )

        assert response.status_code == 400
        assert "Authentication Failed" in response.text
        assert "access_denied" in response.text
        assert "User denied access" in response.text

    def test_callback_missing_code(self, client: TestClient):
        """Test callback without authorization code."""
        response = client.get("/.auth/callback", params={"state": "some_state"})

        assert response.status_code == 400
        assert "Missing code or state parameter" in response.text

    def test_callback_missing_state(self, client: TestClient):
        """Test callback without state parameter."""
        response = client.get("/.auth/callback", params={"code": "some_code"})

        assert response.status_code == 400
        assert "Missing code or state parameter" in response.text

    def test_callback_invalid_state(self, client: TestClient):
        """Test callback with invalid/unknown state."""
        response = client.get("/.auth/callback", params={"code": "auth_code", "state": "unknown_state"})

        assert response.status_code == 400
        assert "Invalid or Expired State" in response.text

    def test_callback_expired_state(self, client: TestClient):
        """Test callback with expired state."""
        state = "expired_state"
        _oauth_states[state] = {
            "user_id": "user_123",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=15),  # Expired
        }

        response = client.get("/.auth/callback", params={"code": "auth_code", "state": state})

        assert response.status_code == 400
        assert "State Expired" in response.text

    async def test_callback_exchange_failure(self, client: TestClient, test_app: Starlette):
        """Test callback when token exchange fails."""
        state = "test_state_123"
        _oauth_states[state] = {
            "user_id": "user_123",
            "interaction_id": None,
            "created_at": datetime.now(),
        }

        # Mock exchange to fail
        with patch.object(
            test_app.state.oauth_client, "exchange_code", new_callable=AsyncMock
        ) as mock_exchange:
            mock_exchange.side_effect = Exception("Token exchange failed")

            response = client.get("/.auth/callback", params={"code": "bad_code", "state": state})

            assert response.status_code == 500
            assert "Authentication Failed" in response.text
            assert "Token exchange failed" in response.text


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
        assert "/.auth/login" in paths
        assert "/.auth/callback" in paths

    def test_route_methods(self, oauth_client: AdobeOAuthClient, token_manager: TokenManager):
        """Test that routes use GET method."""
        routes = create_auth_routes(token_manager, oauth_client)

        for route in routes:
            assert "GET" in route.methods


class TestStateCleanup:
    """Test suite for OAuth state cleanup."""

    def test_cleanup_removes_old_states(self, client: TestClient):
        """Test that cleanup removes states older than 10 minutes."""
        from frameio_kit._auth_routes import _cleanup_expired_states

        # Add states with different ages
        _oauth_states["fresh"] = {"user_id": "user1", "interaction_id": None, "created_at": datetime.now()}

        _oauth_states["expired1"] = {
            "user_id": "user2",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=11),
        }

        _oauth_states["expired2"] = {
            "user_id": "user3",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=20),
        }

        assert len(_oauth_states) == 3

        # Run cleanup
        _cleanup_expired_states()

        # Only fresh state should remain
        assert len(_oauth_states) == 1
        assert "fresh" in _oauth_states
        assert "expired1" not in _oauth_states
        assert "expired2" not in _oauth_states

    def test_cleanup_preserves_recent_states(self, client: TestClient):
        """Test that cleanup preserves states within 10 minutes."""
        from frameio_kit._auth_routes import _cleanup_expired_states

        # Add recent states
        _oauth_states["state1"] = {"user_id": "user1", "interaction_id": None, "created_at": datetime.now()}

        _oauth_states["state2"] = {
            "user_id": "user2",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=5),
        }

        _oauth_states["state3"] = {
            "user_id": "user3",
            "interaction_id": None,
            "created_at": datetime.now() - timedelta(minutes=9, seconds=59),
        }

        assert len(_oauth_states) == 3

        # Run cleanup
        _cleanup_expired_states()

        # All states should remain
        assert len(_oauth_states) == 3
