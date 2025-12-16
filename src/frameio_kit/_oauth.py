"""OAuth 2.0 client and token management for Adobe IMS integration.

This module provides OAuth 2.0 authentication support for Adobe Identity Management
System (IMS), including authorization flow, token exchange, and automatic token refresh.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from key_value.aio.protocols import AsyncKeyValue
from pydantic import BaseModel, Field

from ._encryption import TokenEncryption
from ._exceptions import TokenExchangeError, TokenRefreshError

logger = logging.getLogger(__name__)

# Default token expiration time (in seconds) when 'expires_in' is missing from
# token response. Adobe IMS tokens typically expire in 1 hour (3600 seconds).
DEFAULT_TOKEN_EXPIRES_SECONDS = 3600


class TokenData(BaseModel):
    """OAuth token data model for secure storage.

    Attributes:
        access_token: The OAuth access token used for API authentication.
        refresh_token: The OAuth refresh token used to obtain new access tokens.
        expires_at: The datetime when the access token expires.
        scopes: List of OAuth scopes granted for this token.
        user_id: The Frame.io user ID associated with this token.
    """

    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: list[str]
    user_id: str

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if the access token is expired or will expire soon.

        Args:
            buffer_seconds: Number of seconds before actual expiration to consider
                the token expired. Defaults to 300 seconds (5 minutes).

        Returns:
            True if the token is expired or will expire within the buffer period.
        """
        return datetime.now() >= (self.expires_at - timedelta(seconds=buffer_seconds))


class OAuthConfig(BaseModel):
    """OAuth configuration for Adobe IMS authentication.

    This configuration is provided at the application level to enable user
    authentication via Adobe Login OAuth 2.0 flow.

    Attributes:
        client_id: Adobe IMS application client ID from Adobe Developer Console.
        client_secret: Adobe IMS application client secret.
        redirect_url: Full OAuth callback URL (e.g., "https://myapp.com/auth/callback").
            If None, the URL will be automatically inferred from incoming requests.
            Set this explicitly when behind a reverse proxy or when the public URL
            differs from what the application sees. Must be registered in Adobe Console.
        scopes: List of OAuth scopes to request. Defaults to Frame.io API access.
        storage: Storage backend instance for persisting encrypted tokens. If None,
            defaults to MemoryStore (in-memory, lost on restart).
        encryption_key: Optional encryption key. If None, uses environment variable
            or generates ephemeral key.
        token_refresh_buffer_seconds: Number of seconds before token expiration to
            trigger automatic refresh. Defaults to 300 seconds (5 minutes). This
            prevents token expiration during ongoing API calls.
        http_client: Optional httpx.AsyncClient for OAuth HTTP requests. If not
            provided, a new client will be created. Providing your own enables
            connection pooling, custom timeouts, and shared configuration.

    Example:
        ```python
        from frameio_kit import App, OAuthConfig
        from key_value.aio.stores.disk import DiskStore
        import httpx

        # Basic configuration
        app = App(
            oauth=OAuthConfig(
                client_id=os.getenv("ADOBE_CLIENT_ID"),
                client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
            )
        )

        # Full configuration
        app = App(
            oauth=OAuthConfig(
                client_id=os.getenv("ADOBE_CLIENT_ID"),
                client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
                redirect_url="https://myapp.com/auth/callback",
                storage=DiskStore(directory="./tokens"),
                token_refresh_buffer_seconds=600,  # Refresh 10 minutes early
                http_client=httpx.AsyncClient(timeout=60.0),
            )
        )
        ```
    """

    model_config = {"arbitrary_types_allowed": True}

    client_id: str
    client_secret: str
    redirect_url: str | None = None
    scopes: list[str] = Field(
        default_factory=lambda: ["additional_info.roles", "offline_access", "profile", "email", "openid"]
    )
    storage: Optional[AsyncKeyValue] = None
    encryption_key: Optional[str] = None
    token_refresh_buffer_seconds: int = 300  # 5 minutes default
    http_client: Optional[httpx.AsyncClient] = None


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
            scopes=["openid", "frameio.api"]
        )

        redirect_uri = "https://myapp.com/auth/callback"

        # Generate authorization URL
        auth_url = oauth_client.get_authorization_url("random_state", redirect_uri)

        # Exchange code for tokens
        token_data = await oauth_client.exchange_code("authorization_code", redirect_uri)

        # Refresh token
        new_token = await oauth_client.refresh_token(token_data.refresh_token)
        ```
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize Adobe OAuth client.

        Args:
            client_id: Adobe IMS application client ID.
            client_secret: Adobe IMS application client secret.
            scopes: List of OAuth scopes. Defaults to Frame.io API access.
            http_client: Optional httpx.AsyncClient for HTTP requests. If not provided,
                a new client will be created with default settings (30s timeout).
                Providing your own client allows connection pooling and custom configuration.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or ["additional_info.roles", "offline_access", "profile", "email", "openid"]

        # Adobe IMS OAuth 2.0 endpoints
        self.authorization_url = "https://ims-na1.adobelogin.com/ims/authorize/v2"
        self.token_url = "https://ims-na1.adobelogin.com/ims/token/v3"

        # Use provided client or create our own
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self._owns_http_client = http_client is None  # Track if we should close it

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Generate OAuth authorization URL for user redirect.

        Args:
            state: CSRF protection token (should be random and verified on callback).
            redirect_uri: OAuth callback URI (must match Adobe Console configuration).

        Returns:
            Complete authorization URL to redirect the user to.

        Example:
            ```python
            state = secrets.token_urlsafe(32)
            auth_url = oauth_client.get_authorization_url(
                state,
                "https://myapp.com/auth/callback"
            )
            # Redirect user to auth_url
            ```
        """
        params = httpx.QueryParams(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(self.scopes),
                "response_type": "code",
                "state": state,
            }
        )
        return f"{self.authorization_url}?{params}"

    def _parse_token_response(self, response: dict[str, Any], fallback_refresh_token: str | None = None) -> TokenData:
        """Parse and validate a token response from Adobe IMS.

        Args:
            response: The JSON response from the token endpoint.
            fallback_refresh_token: Refresh token to use if not in response
                (for token refresh where new refresh token may not be returned).

        Returns:
            Validated TokenData.

        Raises:
            TokenExchangeError: If required fields are missing or invalid.
        """
        # Validate access_token
        access_token = response.get("access_token")
        if not access_token:
            raise TokenExchangeError("Missing 'access_token' in token response")

        # Validate refresh_token
        refresh_token = response.get("refresh_token") or fallback_refresh_token
        if not refresh_token:
            raise TokenExchangeError("Missing 'refresh_token' in token response")

        # Validate expires_in
        expires_in = response.get("expires_in")
        if expires_in is None:
            logger.warning("Missing 'expires_in' in token response, defaulting to %d", DEFAULT_TOKEN_EXPIRES_SECONDS)
            expires_in = DEFAULT_TOKEN_EXPIRES_SECONDS
        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError):
            raise TokenExchangeError(f"Invalid 'expires_in' value: {expires_in}")
        if expires_in <= 0:
            raise TokenExchangeError(f"'expires_in' must be positive, got: {expires_in}")

        # Parse scopes from space-separated string. Filter empty strings to handle
        # edge cases like extra whitespace or empty scope responses from the API.
        scope_str = response.get("scope", "")
        scopes = [s for s in scope_str.split() if s]

        return TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now() + timedelta(seconds=expires_in),
            scopes=scopes,
            user_id="",  # Will be set by TokenManager
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> TokenData:
        """Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback.
            redirect_uri: OAuth callback URI (must match the one used in authorization).

        Returns:
            TokenData containing access token, refresh token, and metadata.

        Raises:
            TokenExchangeError: If token response validation fails.
            httpx.HTTPStatusError: If HTTP request fails.

        Example:
            ```python
            # After user authorizes and is redirected with code
            token_data = await oauth_client.exchange_code(
                code,
                "https://myapp.com/auth/callback"
            )
            print(f"Access token expires at: {token_data.expires_at}")
            ```
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        response = await self._http.post(self.token_url, data=data)
        response.raise_for_status()

        token_response = response.json()
        return self._parse_token_response(token_response)

    async def refresh_token(self, refresh_token: str) -> TokenData:
        """Refresh access token using refresh token.

        Args:
            refresh_token: The refresh token from a previous token response.

        Returns:
            TokenData with new access token and updated expiration.

        Raises:
            TokenExchangeError: If token response validation fails.
            httpx.HTTPStatusError: If HTTP request fails (e.g., revoked token).

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
        # Pass the current refresh_token as fallback since refresh responses
        # may not include a new refresh_token
        return self._parse_token_response(token_response, fallback_refresh_token=refresh_token)

    async def close(self) -> None:
        """Close HTTP client and cleanup resources.

        Only closes the HTTP client if it was created internally. If a client was
        provided by the user, it's their responsibility to close it.

        Example:
            ```python
            await oauth_client.close()
            ```
        """
        if self._owns_http_client:
            await self._http.aclose()


class TokenManager:
    """Manages OAuth token lifecycle including storage, retrieval, and refresh.

    This class handles encrypted token storage, automatic refresh, and provides
    a unified interface for token operations.

    Attributes:
        storage: Storage backend instance (py-key-value-aio compatible).
        encryption: TokenEncryption instance for encrypting tokens at rest.
        token_refresh_buffer_seconds: Seconds before expiration to trigger refresh.

    Example:
        ```python
        from key_value.aio.stores.memory import MemoryStore

        token_manager = TokenManager(
            storage=MemoryStore(),
            encryption=TokenEncryption(),
            client_id="your_client_id",
            client_secret="your_client_secret",
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
        storage: AsyncKeyValue,
        encryption: TokenEncryption,
        client_id: str,
        client_secret: str,
        scopes: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        token_refresh_buffer_seconds: int = 300,
    ) -> None:
        """Initialize TokenManager.

        Args:
            storage: py-key-value-aio compatible storage backend.
            encryption: TokenEncryption instance.
            client_id: Adobe IMS client ID (for creating OAuth client when needed).
            client_secret: Adobe IMS client secret (for creating OAuth client when needed).
            scopes: OAuth scopes (for creating OAuth client when needed).
            http_client: Optional httpx.AsyncClient (for creating OAuth client when needed).
            token_refresh_buffer_seconds: Seconds before expiration to refresh tokens.
                Defaults to 300 seconds (5 minutes).
        """
        self.storage = storage
        self.encryption = encryption
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes
        self._http_client = http_client
        self.token_refresh_buffer_seconds = token_refresh_buffer_seconds
        self._oauth_client: AdobeOAuthClient | None = None

    def _get_oauth_client(self) -> AdobeOAuthClient:
        """Get or create the OAuth client for token refresh operations."""
        if self._oauth_client is None:
            self._oauth_client = AdobeOAuthClient(
                client_id=self._client_id,
                client_secret=self._client_secret,
                scopes=self._scopes,
                http_client=self._http_client,
            )
        return self._oauth_client

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

        # Check if needs refresh using configured buffer
        if token_data.is_expired(buffer_seconds=self.token_refresh_buffer_seconds):
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
        # Ensure TTL is never negative (can happen with already-expired tokens during testing)
        ttl = max(0, int((token_data.expires_at - datetime.now()).total_seconds()) + 86400)

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
        oauth_client = self._get_oauth_client()
        new_token = await oauth_client.refresh_token(old_token.refresh_token)
        new_token.user_id = old_token.user_id
        return new_token


def infer_oauth_url(request, path: str) -> str:
    """Infer an OAuth URL from an incoming request.

    Extracts the base URL (scheme + netloc) and mount prefix from the request,
    then constructs the specified OAuth path.

    Args:
        request: Starlette Request object.
        path: The OAuth path to construct (e.g., "/auth/login", "/auth/callback").

    Returns:
        Full URL to the OAuth endpoint.

    Example:
        # App mounted at root, request to /auth/login
        infer_oauth_url(request, "/auth/callback") -> "https://example.com/auth/callback"

        # App mounted at /frameio, request to /frameio/auth/login
        infer_oauth_url(request, "/auth/callback") -> "https://example.com/frameio/auth/callback"

        # App mounted at /frameio, request to /frameio/ (main handler)
        infer_oauth_url(request, "/auth/login") -> "https://example.com/frameio/auth/login"
    """
    base = f"{request.url.scheme}://{request.url.netloc}"
    current_path = str(request.url.path)

    # Extract mount prefix by removing known OAuth paths or trailing slash
    if current_path.endswith("/auth/login"):
        mount_prefix = current_path.removesuffix("/auth/login")
    elif current_path.endswith("/auth/callback"):
        mount_prefix = current_path.removesuffix("/auth/callback")
    elif current_path.endswith("/"):
        mount_prefix = current_path.rstrip("/")
    else:
        # Unknown path, assume root mount
        mount_prefix = ""

    return f"{base}{mount_prefix}{path}"


def get_oauth_redirect_url(oauth_config: OAuthConfig, request) -> str:
    """Get the OAuth redirect URL, using explicit config or inferring from request.

    Args:
        oauth_config: OAuth configuration.
        request: Starlette Request object.

    Returns:
        Full URL to the OAuth callback endpoint.
    """
    if oauth_config.redirect_url:
        return oauth_config.redirect_url
    return infer_oauth_url(request, "/auth/callback")
