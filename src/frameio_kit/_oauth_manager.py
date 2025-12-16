"""OAuth lifecycle management for Frame.io Kit.

This module provides a unified interface for managing OAuth components,
including token storage, encryption, and the OAuth client lifecycle.
"""

import logging
from typing import TYPE_CHECKING

from ._encryption import TokenEncryption
from ._oauth import AdobeOAuthClient, OAuthConfig, TokenManager

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue

logger = logging.getLogger(__name__)


class OAuthManager:
    """Manages OAuth component lifecycle and configuration.

    This class encapsulates the initialization and cleanup of OAuth-related
    components, providing a single point of management for:
    - Token encryption
    - Token storage
    - Token manager
    - OAuth client

    Attributes:
        config: The OAuth configuration.
        token_manager: Manager for token lifecycle operations.
        oauth_client: Client for OAuth flow operations.

    Example:
        ```python
        oauth = OAuthManager(OAuthConfig(
            client_id="...",
            client_secret="...",
        ))

        # Use the token manager
        token = await oauth.token_manager.get_token("user_123")

        # Cleanup
        await oauth.close()
        ```
    """

    def __init__(self, config: OAuthConfig) -> None:
        """Initialize OAuth components from configuration.

        Args:
            config: OAuth configuration containing credentials and settings.
        """
        self.config = config

        # Use provided storage or default to MemoryStore
        storage: "AsyncKeyValue"
        if config.storage is None:
            from key_value.aio.stores.memory import MemoryStore

            storage = MemoryStore()
            logger.info("Using in-memory storage for OAuth tokens (not persistent)")
        else:
            storage = config.storage

        # Initialize encryption
        encryption = TokenEncryption(key=config.encryption_key)

        # Initialize token manager
        self.token_manager = TokenManager(
            storage=storage,
            encryption=encryption,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=config.scopes,
            http_client=config.http_client,
            token_refresh_buffer_seconds=config.token_refresh_buffer_seconds,
        )

        # Create shared OAuth client
        self.oauth_client = AdobeOAuthClient(
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=config.scopes,
            http_client=config.http_client,
        )

        logger.debug("OAuth manager initialized with client_id=%s", config.client_id)

    async def close(self) -> None:
        """Close OAuth client and cleanup resources.

        This method should be called during application shutdown to ensure
        proper cleanup of HTTP connections.
        """
        try:
            await self.oauth_client.close()
            logger.debug("OAuth client closed")
        except Exception:
            logger.exception("Error closing OAuth client")
