"""OAuth 2.0 authentication flow for Frame.io user authorization.

This module provides OAuth capabilities for Frame.io apps that need to act on
behalf of users. It handles the authorization URL generation, token exchange,
and token refresh flows required for user-based authentication.

Example:
    ```python
    from frameio_kit import App, RequireAuth

    @app.on_action(...)
    async def my_action(event: ActionEvent):
        # Check if user has authorized
        user_token = await app.oauth.get_user_token(event.user.id)
        
        if not user_token:
            # Simply return RequireAuth() - framework handles the rest
            return RequireAuth()
        
        # User is authorized - proceed with action
        user_client = await app.get_user_client(event.user.id)
        # ... perform action ...
    ```
"""

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel


class RequireAuth:
    """Signal that user authorization is required.

    Return this from an action handler to indicate that the user needs to
    authorize. The framework will automatically generate an authorization URL
    and return a Message to the user with instructions.

    Attributes:
        title: Optional custom title for the authorization message.
        description: Optional custom description for the authorization message.
            If not provided, a default message with the auth URL is generated.

    Example:
        ```python
        @app.on_action(...)
        async def my_action(event: ActionEvent):
            user_token = await app.oauth.get_user_token(event.user.id)
            
            if not user_token:
                return RequireAuth()
            
            # ... proceed with action ...
        ```

        With custom message:
        ```python
        return RequireAuth(
            title="Connect Your Account",
            description="To export files, we need access to your Frame.io account."
        )
        ```
    """

    def __init__(self, title: str | None = None, description: str | None = None):
        """Initialize RequireAuth signal.

        Args:
            title: Optional custom title for the authorization message.
            description: Optional custom description template. The auth URL
                will be appended to this description automatically.
        """
        self.title = title
        self.description = description


class TokenData(BaseModel):
    """OAuth token data returned from Frame.io.

    Attributes:
        access_token: The access token for API requests.
        refresh_token: The refresh token for obtaining new access tokens.
        expires_in: The number of seconds until the access token expires.
        token_type: The type of token (typically "Bearer").
    """

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str


class TokenStore(ABC):
    """Abstract base class for token storage implementations.

    Developers must implement this interface to provide custom token storage
    for their application (e.g., database, Redis, etc.).
    """

    @abstractmethod
    async def save_token(self, user_id: str, token_data: dict[str, Any]) -> None:
        """Save token data for a user.

        Args:
            user_id: The Frame.io user ID.
            token_data: Dictionary containing access_token, refresh_token,
                expires_in, and token_type.
        """
        pass

    @abstractmethod
    async def get_token(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve token data for a user.

        Args:
            user_id: The Frame.io user ID.

        Returns:
            Dictionary containing token data, or None if not found.
        """
        pass


class OAuthManager:
    """Manages OAuth 2.0 flows for Frame.io user authorization.

    This class handles generating authorization URLs, exchanging authorization
    codes for tokens, and refreshing expired tokens.
    """

    AUTH_URL = "https://applications.frame.io/oauth2/auth"
    TOKEN_URL = "https://applications.frame.io/oauth2/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_store: TokenStore | None = None,
    ):
        """Initialize the OAuth manager.

        Args:
            client_id: The OAuth client ID from Frame.io Developer Console.
            client_secret: The OAuth client secret from Frame.io Developer Console.
            redirect_uri: The redirect URI registered with your Frame.io app.
            token_store: Optional token store for saving and retrieving tokens.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_store = token_store
        self._http_client = httpx.AsyncClient()

    def get_authorization_url(self, state: str | None = None, scope: str = "asset.create") -> str:
        """Generate an OAuth authorization URL.

        Args:
            state: Optional state parameter for CSRF protection. This should
                typically include the user_id and interaction_id to correlate
                the callback with the original action request.
            scope: The OAuth scope to request. Defaults to "asset.create".

        Returns:
            The full authorization URL to redirect the user to.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": scope,
        }
        if state:
            params["state"] = state

        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> TokenData:
        """Exchange an authorization code for access and refresh tokens.

        Args:
            code: The authorization code received from the OAuth callback.

        Returns:
            TokenData containing the access token, refresh token, and metadata.

        Raises:
            httpx.HTTPStatusError: If the token exchange request fails.
        """
        response = await self._http_client.post(
            self.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return TokenData.model_validate(response.json())

    async def refresh_token(self, refresh_token: str) -> TokenData:
        """Refresh an expired access token using a refresh token.

        Args:
            refresh_token: The refresh token obtained during initial authorization.

        Returns:
            TokenData containing the new access token and refresh token.

        Raises:
            httpx.HTTPStatusError: If the refresh request fails.
        """
        response = await self._http_client.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return TokenData.model_validate(response.json())

    async def get_user_token(self, user_id: str) -> str | None:
        """Retrieve a valid access token for a user, refreshing if necessary.

        This method fetches the token from storage and automatically refreshes
        it if it has expired.

        Args:
            user_id: The Frame.io user ID.

        Returns:
            A valid access token, or None if no token is stored for the user.

        Raises:
            RuntimeError: If token_store was not configured.
        """
        if not self.token_store:
            raise RuntimeError("TokenStore not configured. Cannot retrieve user tokens.")

        token_data = await self.token_store.get_token(user_id)
        if not token_data:
            return None

        # TODO: In a production implementation, you would check if the token
        # is expired by storing the expiration timestamp and comparing it
        # with the current time. For now, we return the token as-is.
        # Developers should implement expiration checking in their TokenStore.

        return token_data.get("access_token")

    async def close(self) -> None:
        """Close the HTTP client."""
        if not self._http_client.is_closed:
            await self._http_client.aclose()
