"""Unit tests for OAuth client and token manager."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from key_value.aio.stores.memory import MemoryStore

from frameio_kit._encryption import TokenEncryption
from frameio_kit._oauth import AdobeOAuthClient, OAuthConfig, TokenData, TokenManager, TokenRefreshError


@pytest.fixture
def oauth_config() -> OAuthConfig:
    """Create sample OAuth configuration."""
    return OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_url="https://example.com/auth/callback",
        scopes=["openid", "AdobeID", "frameio.api"],
    )


@pytest.fixture
def oauth_client(oauth_config: OAuthConfig) -> AdobeOAuthClient:
    """Create AdobeOAuthClient instance."""
    return AdobeOAuthClient(
        client_id=oauth_config.client_id,
        client_secret=oauth_config.client_secret,
        scopes=oauth_config.scopes,
    )


@pytest.fixture
async def token_manager() -> TokenManager:
    """Create TokenManager with in-memory storage."""
    storage = MemoryStore()
    encryption = TokenEncryption(key=TokenEncryption.generate_key())
    return TokenManager(
        storage=storage,
        encryption=encryption,
        client_id="test_client_id",
        client_secret="test_client_secret",
    )


@pytest.fixture
def sample_token_data() -> TokenData:
    """Create sample TokenData."""
    return TokenData(
        access_token="sample_access_token",
        refresh_token="sample_refresh_token",
        expires_at=datetime.now() + timedelta(hours=24),
        scopes=["openid", "AdobeID", "frameio.api"],
        user_id="user_123",
    )


class TestAdobeOAuthClient:
    """Test suite for AdobeOAuthClient."""

    def test_initialization(self, oauth_client: AdobeOAuthClient):
        """Test OAuth client initialization."""
        assert oauth_client.client_id == "test_client_id"
        assert oauth_client.client_secret == "test_client_secret"
        assert oauth_client.scopes == ["openid", "AdobeID", "frameio.api"]
        assert oauth_client.authorization_url == "https://ims-na1.adobelogin.com/ims/authorize/v2"
        assert oauth_client.token_url == "https://ims-na1.adobelogin.com/ims/token/v3"

    def test_get_authorization_url(self, oauth_client: AdobeOAuthClient):
        """Test authorization URL generation."""
        state = "test_state_token_12345"
        redirect_uri = "https://example.com/auth/callback"
        auth_url = oauth_client.get_authorization_url(state, redirect_uri)

        # Verify URL structure
        assert auth_url.startswith("https://ims-na1.adobelogin.com/ims/authorize/v2?")
        assert "client_id=test_client_id" in auth_url
        assert "redirect_uri=https%3A%2F%2Fexample.com%2Fauth%2Fcallback" in auth_url
        assert "scope=openid+AdobeID+frameio.api" in auth_url
        assert "response_type=code" in auth_url
        assert f"state={state}" in auth_url

    async def test_exchange_code_success(self, oauth_client: AdobeOAuthClient):
        """Test successful authorization code exchange."""
        mock_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 86400,
            "scope": "openid AdobeID frameio.api",
        }

        redirect_uri = "https://example.com/auth/callback"

        with patch.object(oauth_client._http, "post", new_callable=AsyncMock) as mock_post:
            # Create mock response object
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_post.return_value = mock_resp

            token_data = await oauth_client.exchange_code("auth_code_123", redirect_uri)

            # Verify token data
            assert token_data.access_token == "new_access_token"
            assert token_data.refresh_token == "new_refresh_token"
            assert token_data.scopes == ["openid", "AdobeID", "frameio.api"]
            assert token_data.user_id == ""  # Will be set by TokenManager

            # Verify expiration is approximately 24 hours from now
            time_diff = token_data.expires_at - datetime.now()
            assert 86390 <= time_diff.total_seconds() <= 86410  # Allow 10 second variance

            # Verify HTTP call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == oauth_client.token_url
            assert call_args[1]["data"]["grant_type"] == "authorization_code"
            assert call_args[1]["data"]["code"] == "auth_code_123"
            assert call_args[1]["data"]["client_id"] == "test_client_id"
            assert call_args[1]["data"]["redirect_uri"] == redirect_uri

    async def test_exchange_code_failure(self, oauth_client: AdobeOAuthClient):
        """Test failed authorization code exchange."""
        redirect_uri = "https://example.com/auth/callback"

        with patch.object(oauth_client._http, "post", new_callable=AsyncMock) as mock_post:
            # Create mock response that raises error
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError("Invalid code", request=MagicMock(), response=MagicMock())
            )
            mock_post.return_value = mock_resp

            with pytest.raises(httpx.HTTPStatusError):
                await oauth_client.exchange_code("invalid_code", redirect_uri)

    async def test_refresh_token_success(self, oauth_client: AdobeOAuthClient):
        """Test successful token refresh."""
        mock_response = {
            "access_token": "refreshed_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 86400,
            "scope": "openid AdobeID frameio.api",
        }

        with patch.object(oauth_client._http, "post", new_callable=AsyncMock) as mock_post:
            # Create mock response object
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_post.return_value = mock_resp

            token_data = await oauth_client.refresh_token("old_refresh_token")

            # Verify token data
            assert token_data.access_token == "refreshed_access_token"
            assert token_data.refresh_token == "new_refresh_token"

            # Verify HTTP call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[1]["data"]["grant_type"] == "refresh_token"
            assert call_args[1]["data"]["refresh_token"] == "old_refresh_token"

    async def test_refresh_token_without_new_refresh_token(self, oauth_client: AdobeOAuthClient):
        """Test token refresh when Adobe doesn't return new refresh token."""
        mock_response = {
            "access_token": "refreshed_access_token",
            "expires_in": 86400,
            "scope": "openid AdobeID frameio.api",
        }

        with patch.object(oauth_client._http, "post", new_callable=AsyncMock) as mock_post:
            # Create mock response object
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_post.return_value = mock_resp

            token_data = await oauth_client.refresh_token("same_refresh_token")

            # Should reuse the old refresh token
            assert token_data.refresh_token == "same_refresh_token"

    async def test_refresh_token_failure(self, oauth_client: AdobeOAuthClient):
        """Test failed token refresh (revoked token)."""
        with patch.object(oauth_client._http, "post", new_callable=AsyncMock) as mock_post:
            # Create mock response that raises error
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError("Invalid refresh token", request=MagicMock(), response=MagicMock())
            )
            mock_post.return_value = mock_resp

            with pytest.raises(httpx.HTTPStatusError):
                await oauth_client.refresh_token("revoked_token")

    async def test_close(self, oauth_client: AdobeOAuthClient):
        """Test HTTP client cleanup."""
        with patch.object(oauth_client._http, "aclose", new_callable=AsyncMock) as mock_close:
            await oauth_client.close()
            mock_close.assert_called_once()


class TestTokenManager:
    """Test suite for TokenManager."""

    async def test_store_and_get_token(self, token_manager: TokenManager, sample_token_data: TokenData):
        """Test storing and retrieving a token."""
        user_id = "user_123"

        # Store token
        await token_manager.store_token(user_id, sample_token_data)

        # Retrieve token
        retrieved = await token_manager.get_token(user_id)

        assert retrieved is not None
        assert retrieved.user_id == user_id
        assert retrieved.access_token == sample_token_data.access_token
        assert retrieved.refresh_token == sample_token_data.refresh_token
        assert retrieved.scopes == sample_token_data.scopes

    async def test_get_token_nonexistent_user(self, token_manager: TokenManager):
        """Test getting token for user who never authenticated."""
        token = await token_manager.get_token("nonexistent_user")
        assert token is None

    async def test_delete_token(self, token_manager: TokenManager, sample_token_data: TokenData):
        """Test token deletion."""
        user_id = "user_123"

        # Store and verify
        await token_manager.store_token(user_id, sample_token_data)
        assert await token_manager.get_token(user_id) is not None

        # Delete
        await token_manager.delete_token(user_id)

        # Verify deletion
        assert await token_manager.get_token(user_id) is None

    async def test_auto_refresh_expired_token(self, token_manager: TokenManager):
        """Test automatic token refresh when expired."""
        user_id = "user_123"

        # Create expired token
        expired_token = TokenData(
            access_token="expired_access",
            refresh_token="valid_refresh",
            expires_at=datetime.now() - timedelta(hours=1),  # Expired 1 hour ago
            scopes=["openid"],
            user_id=user_id,
        )

        # Mock refresh to return new token
        new_token = TokenData(
            access_token="refreshed_access",
            refresh_token="new_refresh",
            expires_at=datetime.now() + timedelta(hours=24),
            scopes=["openid"],
            user_id=user_id,
        )

        # Create mock OAuth client
        mock_oauth_client = MagicMock()
        mock_refresh = AsyncMock(return_value=new_token)
        mock_oauth_client.refresh_token = mock_refresh

        with patch.object(token_manager, "_get_oauth_client", return_value=mock_oauth_client):
            # Store expired token
            await token_manager.store_token(user_id, expired_token)

            # Get token should trigger refresh
            retrieved = await token_manager.get_token(user_id)

            # Verify refresh was called
            mock_refresh.assert_called_once_with("valid_refresh")

            # Verify we got the new token
            assert retrieved is not None
            assert retrieved.access_token == "refreshed_access"
            assert retrieved.refresh_token == "new_refresh"

    async def test_refresh_failure_deletes_token(self, token_manager: TokenManager):
        """Test that failed refresh deletes the token."""
        user_id = "user_123"

        # Create expired token
        expired_token = TokenData(
            access_token="expired_access",
            refresh_token="revoked_refresh",
            expires_at=datetime.now() - timedelta(hours=1),
            scopes=["openid"],
            user_id=user_id,
        )

        # Create mock OAuth client
        mock_oauth_client = MagicMock()
        mock_refresh = AsyncMock(
            side_effect=httpx.HTTPStatusError("Invalid refresh token", request=MagicMock(), response=MagicMock())
        )
        mock_oauth_client.refresh_token = mock_refresh

        with patch.object(token_manager, "_get_oauth_client", return_value=mock_oauth_client):
            # Store expired token
            await token_manager.store_token(user_id, expired_token)

            # Get token should trigger refresh and raise error
            with pytest.raises(TokenRefreshError, match="Failed to refresh token"):
                await token_manager.get_token(user_id)

            # Token should be deleted after failed refresh
            assert await token_manager.get_token(user_id) is None

    async def test_token_with_buffer_not_refreshed(self, token_manager: TokenManager):
        """Test that tokens expiring within buffer time are refreshed."""
        user_id = "user_123"

        # Create token expiring in 2 minutes (within 5 minute buffer)
        near_expiry_token = TokenData(
            access_token="near_expiry_access",
            refresh_token="valid_refresh",
            expires_at=datetime.now() + timedelta(minutes=2),
            scopes=["openid"],
            user_id=user_id,
        )

        # Mock refresh
        new_token = TokenData(
            access_token="refreshed_access",
            refresh_token="new_refresh",
            expires_at=datetime.now() + timedelta(hours=24),
            scopes=["openid"],
            user_id=user_id,
        )

        # Create mock OAuth client
        mock_oauth_client = MagicMock()
        mock_refresh = AsyncMock(return_value=new_token)
        mock_oauth_client.refresh_token = mock_refresh

        with patch.object(token_manager, "_get_oauth_client", return_value=mock_oauth_client):
            await token_manager.store_token(user_id, near_expiry_token)

            # Get token should trigger refresh due to buffer
            retrieved = await token_manager.get_token(user_id)

            # Verify refresh was called
            mock_refresh.assert_called_once()

            # Verify we got the new token
            assert retrieved is not None
            assert retrieved.access_token == "refreshed_access"

    async def test_make_key(self, token_manager: TokenManager):
        """Test storage key generation."""
        assert token_manager._make_key("user_123") == "user:user_123"
        assert token_manager._make_key("alice") == "user:alice"

    async def test_wrap_unwrap_encrypted_bytes(self, token_manager: TokenManager):
        """Test encryption byte wrapping/unwrapping."""
        test_bytes = b"test_encrypted_data_12345"

        # Wrap
        wrapped = token_manager._wrap_encrypted_bytes(test_bytes)
        assert isinstance(wrapped, dict)
        assert "encrypted_token" in wrapped
        assert isinstance(wrapped["encrypted_token"], str)

        # Unwrap
        unwrapped = token_manager._unwrap_encrypted_bytes(wrapped)
        assert unwrapped == test_bytes


class TestOAuthConfig:
    """Test suite for OAuthConfig model."""

    def test_valid_config(self):
        """Test creating valid OAuth config."""
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url="https://example.com/auth/callback",
        )

        assert config.client_id == "test_id"
        assert config.client_secret == "test_secret"
        assert config.redirect_url == "https://example.com/auth/callback"
        assert config.scopes == ["additional_info.roles", "offline_access", "profile", "email", "openid"]

    def test_config_with_no_redirect_url(self):
        """Test OAuth config without explicit redirect_url (will be inferred at runtime)."""
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url=None,
        )

        assert config.redirect_url is None

    def test_custom_scopes(self):
        """Test OAuth config with custom scopes."""
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url="https://example.com/auth/callback",
            scopes=["openid", "custom_scope"],
        )

        assert config.scopes == ["openid", "custom_scope"]

    def test_storage_default(self):
        """Test that storage defaults to None."""
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url="https://example.com/auth/callback",
        )

        assert config.storage is None

    def test_encryption_key_optional(self):
        """Test that encryption key is optional."""
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url="https://example.com/auth/callback",
            encryption_key="test_key_12345",
        )

        assert config.encryption_key == "test_key_12345"

    def test_http_client_optional(self):
        """Test that http_client is optional and defaults to None."""
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url="https://example.com/auth/callback",
        )

        assert config.http_client is None

    def test_custom_http_client(self):
        """Test that custom http_client can be provided."""
        custom_client = httpx.AsyncClient(timeout=60.0)
        config = OAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_url="https://example.com/auth/callback",
            http_client=custom_client,
        )

        assert config.http_client is custom_client


class TestCustomHttpClient:
    """Tests for custom httpx client support in AdobeOAuthClient."""

    async def test_uses_provided_http_client(self):
        """Test that OAuth client uses provided httpx client."""
        custom_client = httpx.AsyncClient(timeout=60.0)

        oauth_client = AdobeOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            http_client=custom_client,
        )

        # Verify it uses the custom client
        assert oauth_client._http is custom_client
        assert not oauth_client._owns_http_client

        # Close should not close the custom client
        await oauth_client.close()
        # Custom client should still be usable
        assert not custom_client.is_closed

        # Clean up
        await custom_client.aclose()

    async def test_creates_own_client_when_not_provided(self):
        """Test that OAuth client creates its own httpx client when not provided."""
        oauth_client = AdobeOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
        )

        # Verify it created its own client
        assert oauth_client._http is not None
        assert oauth_client._owns_http_client

        # Close should close the owned client
        await oauth_client.close()
        assert oauth_client._http.is_closed

    async def test_custom_client_timeout_respected(self):
        """Test that custom client's timeout configuration is preserved."""
        custom_client = httpx.AsyncClient(timeout=120.0)

        oauth_client = AdobeOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            http_client=custom_client,
        )

        # Verify timeout is preserved
        assert oauth_client._http.timeout.read == 120.0

        # Clean up
        await custom_client.aclose()
