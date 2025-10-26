"""Token storage models and utilities for OAuth authentication.

This module provides data models for storing and managing OAuth tokens,
including functionality for token expiration checking.
"""

from datetime import datetime, timedelta

from pydantic import BaseModel


class TokenData(BaseModel):
    """OAuth token data model for secure storage.

    This model encapsulates all necessary information for OAuth token management,
    including access and refresh tokens, expiration tracking, and associated metadata.

    Attributes:
        access_token: The OAuth access token used for API authentication.
        refresh_token: The OAuth refresh token used to obtain new access tokens.
        expires_at: The datetime when the access token expires.
        scopes: List of OAuth scopes granted for this token.
        user_id: The Frame.io user ID associated with this token.

    Example:
        ```python
        from datetime import datetime, timedelta

        token = TokenData(
            access_token="eyJhbGc...",
            refresh_token="def50200...",
            expires_at=datetime.now() + timedelta(hours=24),
            scopes=["openid", "AdobeID", "frameio.api"],
            user_id="user_abc123"
        )

        if token.is_expired():
            # Token needs refresh
            pass
        ```
    """

    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: list[str]
    user_id: str

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if the access token is expired or will expire soon.

        This method checks expiration with a configurable buffer to allow for
        preemptive token refresh. By default, tokens are considered expired
        5 minutes before their actual expiration time to prevent race conditions
        and API call failures.

        Args:
            buffer_seconds: Number of seconds before actual expiration to consider
                the token expired. Defaults to 300 seconds (5 minutes).

        Returns:
            True if the token is expired or will expire within the buffer period,
            False otherwise.

        Example:
            ```python
            # Check with default 5-minute buffer
            if token.is_expired():
                token = await refresh_token(token.refresh_token)

            # Check with custom 1-minute buffer
            if token.is_expired(buffer_seconds=60):
                token = await refresh_token(token.refresh_token)
            ```
        """
        return datetime.now() >= (self.expires_at - timedelta(seconds=buffer_seconds))
