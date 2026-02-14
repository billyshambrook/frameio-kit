"""OAuth lifecycle management for Frame.io Kit.

This module provides a unified interface for managing OAuth components,
including token storage, encryption, and the OAuth client lifecycle.
"""

import logging
from ._encryption import TokenEncryption
from ._oauth import AdobeOAuthClient, OAuthConfig, StateSerializer, TokenManager
from ._storage import MemoryStorage, Storage

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
    """

    def __init__(
        self,
        config: OAuthConfig,
        storage: Storage | None = None,
        encryption_key: str | None = None,
    ) -> None:
        """Initialize OAuth components from configuration.

        Args:
            config: OAuth configuration containing credentials and settings.
            storage: Storage backend for persisting encrypted tokens. If None,
                defaults to MemoryStorage (in-memory, lost on restart).
            encryption_key: Optional encryption key for token storage. If None,
                uses environment variable or generates ephemeral key.
        """
        self.config = config

        # Use provided storage or default to MemoryStorage
        resolved_storage: Storage
        if storage is None:
            resolved_storage = MemoryStorage()
            logger.info("Using in-memory storage for OAuth tokens (not persistent)")
        else:
            resolved_storage = storage

        # Initialize encryption
        encryption = TokenEncryption(key=encryption_key)

        # Initialize token manager
        self.token_manager = TokenManager(
            storage=resolved_storage,
            encryption=encryption,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=config.scopes,
            ims_url=config.ims_url,
            http_client=config.http_client,
            token_refresh_buffer_seconds=config.token_refresh_buffer_seconds,
        )

        # Create shared OAuth client
        self.oauth_client = AdobeOAuthClient(
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=config.scopes,
            ims_url=config.ims_url,
            http_client=config.http_client,
        )

        # Create state serializer for stateless OAuth state tokens
        self.state_serializer = StateSerializer(secret_key=encryption_key)

        logger.debug("OAuth manager initialized with client_id=%s", config.client_id)

    async def close(self) -> None:
        """Close OAuth client and cleanup resources.

        This method should be called during application shutdown to ensure
        proper cleanup of HTTP connections.

        Raises:
            Exception: Re-raises any exception that occurs during cleanup
                after logging it, allowing callers to track cleanup failures.
        """
        try:
            await self.oauth_client.close()
            logger.debug("OAuth client closed")
        except Exception:
            logger.exception("Error closing OAuth client")
            raise
