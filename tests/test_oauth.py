"""Tests for OAuth functionality in frameio-kit."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from frameio_kit import App, TokenStore
from frameio_kit.oauth import OAuthManager, TokenData


class InMemoryTokenStore(TokenStore):
    """Simple in-memory token store for testing."""

    def __init__(self):
        self.tokens: dict[str, dict[str, Any]] = {}

    async def save_token(self, user_id: str, token_data: dict[str, Any]) -> None:
        self.tokens[user_id] = token_data

    async def get_token(self, user_id: str) -> dict[str, Any] | None:
        return self.tokens.get(user_id)


@pytest.fixture
def oauth_credentials():
    """OAuth credentials for testing."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "redirect_uri": "https://test.example.com/oauth/callback",
    }


@pytest.fixture
def token_store():
    """In-memory token store for testing."""
    return InMemoryTokenStore()


@pytest.fixture
def oauth_manager(oauth_credentials, token_store):
    """OAuth manager instance for testing."""
    return OAuthManager(
        client_id=oauth_credentials["client_id"],
        client_secret=oauth_credentials["client_secret"],
        redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )


def test_get_authorization_url(oauth_manager):
    """Test that authorization URL is generated correctly."""
    url = oauth_manager.get_authorization_url(state="user_123:interaction_456")

    assert "https://applications.frame.io/oauth2/auth" in url
    assert "client_id=test_client_id" in url
    assert "redirect_uri=https%3A%2F%2Ftest.example.com%2Foauth%2Fcallback" in url
    assert "response_type=code" in url
    assert "scope=asset.create" in url
    assert "state=user_123%3Ainteraction_456" in url


def test_get_authorization_url_without_state(oauth_manager):
    """Test that authorization URL works without state parameter."""
    url = oauth_manager.get_authorization_url()

    assert "https://applications.frame.io/oauth2/auth" in url
    assert "client_id=test_client_id" in url
    assert "state" not in url


async def test_exchange_code_for_token(oauth_manager):
    """Test exchanging authorization code for tokens."""
    mock_response = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    with patch.object(oauth_manager._http_client, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_response,
            raise_for_status=lambda: None,
        )

        token_data = await oauth_manager.exchange_code_for_token("test_code")

        assert isinstance(token_data, TokenData)
        assert token_data.access_token == "test_access_token"
        assert token_data.refresh_token == "test_refresh_token"
        assert token_data.expires_in == 3600
        assert token_data.token_type == "Bearer"

        # Verify the request was made correctly
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["data"]["grant_type"] == "authorization_code"
        assert call_kwargs["data"]["code"] == "test_code"


async def test_refresh_token(oauth_manager):
    """Test refreshing an access token."""
    mock_response = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    with patch.object(oauth_manager._http_client, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_response,
            raise_for_status=lambda: None,
        )

        token_data = await oauth_manager.refresh_token("old_refresh_token")

        assert token_data.access_token == "new_access_token"
        assert token_data.refresh_token == "new_refresh_token"

        # Verify the request was made correctly
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["data"]["grant_type"] == "refresh_token"
        assert call_kwargs["data"]["refresh_token"] == "old_refresh_token"


async def test_get_user_token(oauth_manager, token_store):
    """Test retrieving a user token from storage."""
    # Store a token
    await token_store.save_token(
        "user_123",
        {
            "access_token": "stored_token",
            "refresh_token": "stored_refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )

    # Retrieve it
    token = await oauth_manager.get_user_token("user_123")
    assert token == "stored_token"


async def test_get_user_token_not_found(oauth_manager):
    """Test retrieving a token for a user that doesn't exist."""
    token = await oauth_manager.get_user_token("nonexistent_user")
    assert token is None


async def test_app_oauth_property_with_credentials(oauth_credentials, token_store):
    """Test that the oauth property is available when credentials are provided."""
    app = App(
        oauth_client_id=oauth_credentials["client_id"],
        oauth_client_secret=oauth_credentials["client_secret"],
        oauth_redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )

    assert app.oauth is not None
    assert isinstance(app.oauth, OAuthManager)


async def test_app_oauth_property_without_credentials():
    """Test that accessing oauth property raises error when not configured."""
    app = App()

    with pytest.raises(RuntimeError, match="OAuth not configured"):
        _ = app.oauth


async def test_oauth_callback_route(oauth_credentials, token_store):
    """Test the OAuth callback route handler."""
    app = App(
        oauth_client_id=oauth_credentials["client_id"],
        oauth_client_secret=oauth_credentials["client_secret"],
        oauth_redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )

    mock_token_data = {
        "access_token": "callback_access_token",
        "refresh_token": "callback_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    with patch.object(app.oauth._http_client, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_token_data,
            raise_for_status=lambda: None,
        )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            response = await client.get("/oauth/callback?code=test_code&state=user_123:interaction_456")

            assert response.status_code == 200
            assert "Authorization successful" in response.text

            # Verify token was stored
            stored_token = await token_store.get_token("user_123")
            assert stored_token is not None
            assert stored_token["access_token"] == "callback_access_token"


async def test_oauth_callback_route_error(oauth_credentials, token_store):
    """Test the OAuth callback route with an error parameter."""
    app = App(
        oauth_client_id=oauth_credentials["client_id"],
        oauth_client_secret=oauth_credentials["client_secret"],
        oauth_redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/oauth/callback?error=access_denied")

        assert response.status_code == 400
        assert "OAuth error" in response.text


async def test_oauth_callback_route_missing_code(oauth_credentials, token_store):
    """Test the OAuth callback route without a code parameter."""
    app = App(
        oauth_client_id=oauth_credentials["client_id"],
        oauth_client_secret=oauth_credentials["client_secret"],
        oauth_redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/oauth/callback")

        assert response.status_code == 400
        assert "Missing authorization code" in response.text


async def test_get_user_client(oauth_credentials, token_store):
    """Test creating a user-specific client."""
    app = App(
        oauth_client_id=oauth_credentials["client_id"],
        oauth_client_secret=oauth_credentials["client_secret"],
        oauth_redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )

    # Store a token for the user
    await token_store.save_token(
        "user_123",
        {
            "access_token": "user_token",
            "refresh_token": "user_refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )

    # Get a client for the user
    client = await app.get_user_client("user_123")
    assert client is not None


async def test_get_user_client_no_token(oauth_credentials, token_store):
    """Test that get_user_client raises error when no token is found."""
    app = App(
        oauth_client_id=oauth_credentials["client_id"],
        oauth_client_secret=oauth_credentials["client_secret"],
        oauth_redirect_uri=oauth_credentials["redirect_uri"],
        token_store=token_store,
    )

    with pytest.raises(RuntimeError, match="No token found for user"):
        await app.get_user_client("nonexistent_user")
