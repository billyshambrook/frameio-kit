"""OAuth 2.0 client and token management for Adobe IMS integration.

This module provides OAuth 2.0 authentication support for Adobe Identity Management
System (IMS), including authorization flow, token exchange, and automatic token refresh.
"""

from datetime import datetime, timedelta
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from ._encryption import TokenEncryption
from ._storage import TokenData


class OAuthConfig(BaseModel):
    """OAuth configuration for Adobe IMS authentication.

    This configuration is provided at the application level to enable user
    authentication via Adobe Login OAuth 2.0 flow.

    Attributes:
        client_id: Adobe IMS application client ID from Adobe Developer Console.
        client_secret: Adobe IMS application client secret.
        redirect_uri: OAuth callback URI (must be registered in Adobe Console).
        scopes: List of OAuth scopes to request. Defaults to Frame.io API access.
        storage: Storage backend instance for persisting encrypted tokens.
        encryption_key: Optional encryption key. If None, uses environment variable
            or system keyring.

    Example:
        ```python
        from frameio_kit import App, OAuthConfig
        from key_value.aio.stores.memory import MemoryStore

        app = App(
            oauth=OAuthConfig(
                client_id=os.getenv("ADOBE_CLIENT_ID"),
                client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
                redirect_uri="https://myapp.com/.auth/callback",
                storage=MemoryStore(),
            )
        )
        ```
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "AdobeID", "frameio.api"])
    storage: object = Field(default_factory=lambda: None)  # Will be initialized with MemoryStore if None
    encryption_key: Optional[str] = None


class AdobeOAuthClient:
    """OAuth 2.0 client for Adobe Identity Management System (IMS).

    This client handles the OAuth 2.0 authorization code flow with Adobe IMS,
    including authorization URL generation, code exchange, and token refresh.

    Attributes:
        client_id: Adobe IMS application client ID.
        client_secret: Adobe IMS application client secret.
        redirect_uri: OAuth callback URI.
        scopes: List of OAuth scopes to request.
        authorization_url: Adobe IMS authorization endpoint.
        token_url: Adobe IMS token endpoint.

    Example:
        ```python
        oauth_client = AdobeOAuthClient(
            client_id="your_client_id",
            client_secret="your_client_secret",
            redirect_uri="https://myapp.com/.auth/callback",
            scopes=["openid", "frameio.api"]
        )

        # Generate authorization URL
        auth_url = oauth_client.get_authorization_url(state="random_state")

        # Exchange code for tokens
        token_data = await oauth_client.exchange_code("authorization_code")

        # Refresh token
        new_token = await oauth_client.refresh_token(token_data.refresh_token)
        ```
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> None:
        """Initialize Adobe OAuth client.

        Args:
            client_id: Adobe IMS application client ID.
            client_secret: Adobe IMS application client secret.
            redirect_uri: OAuth callback URI (must match Adobe Console configuration).
            scopes: List of OAuth scopes. Defaults to Frame.io API access.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["openid", "AdobeID", "frameio.api"]

        # Adobe IMS OAuth 2.0 endpoints
        self.authorization_url = "https://ims-na1.adobelogin.com/ims/authorize/v2"
        self.token_url = "https://ims-na1.adobelogin.com/ims/token/v3"

        self._http = httpx.AsyncClient(timeout=30.0)

    def get_authorization_url(self, state: str) -> str:
        """Generate OAuth authorization URL for user redirect.

        Args:
            state: CSRF protection token (should be random and verified on callback).

        Returns:
            Complete authorization URL to redirect the user to.

        Example:
            ```python
            state = secrets.token_urlsafe(32)
            auth_url = oauth_client.get_authorization_url(state)
            # Redirect user to auth_url
            ```
        """
        params = httpx.QueryParams(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(self.scopes),
                "response_type": "code",
                "state": state,
            }
        )
        return f"{self.authorization_url}?{params}"

    async def exchange_code(self, code: str) -> TokenData:
        """Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback.

        Returns:
            TokenData containing access token, refresh token, and metadata.

        Raises:
            httpx.HTTPStatusError: If token exchange fails.

        Example:
            ```python
            # After user authorizes and is redirected with code
            token_data = await oauth_client.exchange_code(code)
            print(f"Access token expires at: {token_data.expires_at}")
            ```
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        response = await self._http.post(self.token_url, data=data)
        response.raise_for_status()

        token_response = response.json()
        return TokenData(
            access_token=token_response["access_token"],
            refresh_token=token_response["refresh_token"],
            expires_at=datetime.now() + timedelta(seconds=token_response["expires_in"]),
            scopes=token_response.get("scope", "").split(),
            user_id="",  # Will be set by TokenManager
        )

    async def refresh_token(self, refresh_token: str) -> TokenData:
        """Refresh access token using refresh token.

        Args:
            refresh_token: The refresh token from a previous token response.

        Returns:
            TokenData with new access token and updated expiration.

        Raises:
            httpx.HTTPStatusError: If token refresh fails (e.g., revoked token).

        Example:
            ```python
            if token_data.is_expired():
                new_token = await oauth_client.refresh_token(token_data.refresh_token)
            ```
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        response = await self._http.post(self.token_url, data=data)
        response.raise_for_status()

        token_response = response.json()
        return TokenData(
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token", refresh_token),  # May not return new one
            expires_at=datetime.now() + timedelta(seconds=token_response["expires_in"]),
            scopes=token_response.get("scope", "").split(),
            user_id="",  # Will be set by TokenManager
        )

    async def close(self) -> None:
        """Close HTTP client and cleanup resources.

        Should be called when the OAuth client is no longer needed.

        Example:
            ```python
            await oauth_client.close()
            ```
        """
        await self._http.aclose()


class TokenRefreshError(Exception):
    """Raised when token refresh fails.

    This typically indicates the refresh token has been revoked or expired,
    requiring the user to re-authenticate.
    """

    pass


class TokenManager:
    """Manages OAuth token lifecycle including storage, retrieval, and refresh.

    This class handles encrypted token storage, automatic refresh, and provides
    a unified interface for token operations.

    Attributes:
        storage: Storage backend instance (py-key-value-aio compatible).
        encryption: TokenEncryption instance for encrypting tokens at rest.
        oauth_client: AdobeOAuthClient for refreshing tokens.

    Example:
        ```python
        from key_value.aio.stores.memory import MemoryStore

        token_manager = TokenManager(
            storage=MemoryStore(),
            encryption=TokenEncryption(),
            oauth_client=AdobeOAuthClient(...)
        )

        # Store token after OAuth flow
        await token_manager.store_token("user_123", token_data)

        # Get token (auto-refreshes if expired)
        token = await token_manager.get_token("user_123")

        # Delete token (logout)
        await token_manager.delete_token("user_123")
        ```
    """

    def __init__(
        self,
        storage: object,
        encryption: TokenEncryption,
        oauth_client: AdobeOAuthClient,
    ) -> None:
        """Initialize TokenManager.

        Args:
            storage: py-key-value-aio compatible storage backend.
            encryption: TokenEncryption instance.
            oauth_client: AdobeOAuthClient for token refresh operations.
        """
        self.storage = storage
        self.encryption = encryption
        self.oauth_client = oauth_client

    def _make_key(self, user_id: str) -> str:
        """Create storage key for user token.

        Args:
            user_id: Frame.io user ID.

        Returns:
            Storage key string.
        """
        return f"user:{user_id}"

    def _wrap_encrypted_bytes(self, encrypted_bytes: bytes) -> dict[str, str]:
        """Wrap encrypted bytes in dict format for py-key-value-aio stores.

        Args:
            encrypted_bytes: Fernet-encrypted token data.

        Returns:
            Dictionary with base64-encoded encrypted data.
        """
        import base64

        return {"encrypted_token": base64.b64encode(encrypted_bytes).decode("utf-8")}

    def _unwrap_encrypted_bytes(self, data: dict[str, str]) -> bytes:
        """Unwrap encrypted bytes from py-key-value-aio dict format.

        Args:
            data: Dictionary from storage containing encrypted token.

        Returns:
            Encrypted bytes ready for decryption.
        """
        import base64

        return base64.b64decode(data["encrypted_token"])

    async def get_token(self, user_id: str) -> Optional[TokenData]:
        """Get valid token for user, refreshing if necessary.

        This method retrieves the token from storage, checks if it's expired,
        and automatically refreshes it if needed. Returns None if the user
        has never authenticated.

        Args:
            user_id: Frame.io user ID.

        Returns:
            Valid TokenData or None if user never authenticated.

        Raises:
            TokenRefreshError: If token refresh fails (requires re-authentication).

        Example:
            ```python
            token = await token_manager.get_token("user_123")
            if token is None:
                # User needs to authenticate
                pass
            else:
                # Use token.access_token for API calls
                pass
            ```
        """
        key = self._make_key(user_id)
        encrypted_dict = await self.storage.get(key)

        if encrypted_dict is None:
            return None

        encrypted = self._unwrap_encrypted_bytes(encrypted_dict)
        token_data = self.encryption.decrypt(encrypted)

        # Check if needs refresh
        if token_data.is_expired():
            try:
                token_data = await self._refresh_token(token_data)
                await self.store_token(user_id, token_data)
            except Exception as e:
                # Refresh failed - token may be revoked
                await self.storage.delete(key)
                raise TokenRefreshError(f"Failed to refresh token for user {user_id}") from e

        return token_data

    async def store_token(self, user_id: str, token_data: TokenData) -> None:
        """Store encrypted token for user.

        Args:
            user_id: Frame.io user ID.
            token_data: TokenData to store.

        Example:
            ```python
            # After successful OAuth flow
            token_data.user_id = user_id
            await token_manager.store_token(user_id, token_data)
            ```
        """
        token_data.user_id = user_id
        key = self._make_key(user_id)

        encrypted = self.encryption.encrypt(token_data)
        wrapped = self._wrap_encrypted_bytes(encrypted)

        # TTL: token lifetime + 1 day buffer for refresh
        ttl = int((token_data.expires_at - datetime.now()).total_seconds()) + 86400

        await self.storage.put(key, wrapped, ttl=ttl)

    async def delete_token(self, user_id: str) -> None:
        """Remove token for user (logout).

        Args:
            user_id: Frame.io user ID.

        Example:
            ```python
            # User logout
            await token_manager.delete_token("user_123")
            ```
        """
        key = self._make_key(user_id)
        await self.storage.delete(key)

    async def _refresh_token(self, old_token: TokenData) -> TokenData:
        """Refresh an expired token.

        Args:
            old_token: Expired TokenData with valid refresh_token.

        Returns:
            New TokenData with fresh access token.

        Raises:
            Exception: If refresh fails.
        """
        new_token = await self.oauth_client.refresh_token(old_token.refresh_token)
        new_token.user_id = old_token.user_id
        return new_token
