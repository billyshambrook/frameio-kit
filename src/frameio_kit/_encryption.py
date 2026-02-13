"""Token encryption utilities for secure OAuth token storage.

This module provides Fernet symmetric encryption for protecting OAuth tokens at rest.
Encryption keys can be provided explicitly, loaded from environment variables,
or generated ephemerally with warnings.
"""

import logging
import os
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Encrypts and decrypts data using Fernet symmetric encryption.

    Supports multiple key sources with a clear hierarchy to balance
    security and developer experience.

    Key Loading Hierarchy:
        1. Explicit key parameter (highest priority)
        2. FRAMEIO_AUTH_ENCRYPTION_KEY environment variable
        3. Ephemeral key generation with warning (lowest priority)

    Attributes:
        _key: The Fernet encryption key (bytes).
        _fernet: The Fernet encryption instance.

    Example:
        ```python
        encryption = TokenEncryption()
        encrypted = encryption.encrypt(b"secret data")
        decrypted = encryption.decrypt(encrypted)
        ```

    Warning:
        In production, always set FRAMEIO_AUTH_ENCRYPTION_KEY environment variable.
        Ephemeral keys will cause tokens to be lost on application restart.
    """

    def __init__(self, key: str | None = None) -> None:
        """Initialize encryption with a Fernet key.

        The key is loaded from the first available source:
        1. The `key` parameter if provided
        2. FRAMEIO_AUTH_ENCRYPTION_KEY environment variable
        3. Generated ephemerally with warning

        Args:
            key: Optional Base64-encoded Fernet key. If provided, takes precedence
                over all other key sources. Can be generated using
                `TokenEncryption.generate_key()`.

        Example:
            ```python
            # Explicit key (production)
            encryption = TokenEncryption(key=os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"))

            # Auto-load from environment
            encryption = TokenEncryption()

            # Generate new key for production
            key = TokenEncryption.generate_key()
            print(f"Store this key: {key}")
            encryption = TokenEncryption(key=key)
            ```
        """
        if key:
            self._key = key.encode() if isinstance(key, str) else key
        elif key_from_env := os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"):
            self._key = key_from_env.encode()
        else:
            # Generate ephemeral key with warning
            logger.warning(
                "No encryption key configured. "
                "Using ephemeral key - tokens will be lost on restart. "
                "Set FRAMEIO_AUTH_ENCRYPTION_KEY in production."
            )
            self._key = Fernet.generate_key()

        self._fernet = Fernet(self._key)

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt bytes using Fernet symmetric encryption.

        Args:
            data: The plaintext bytes to encrypt.

        Returns:
            Encrypted bytes suitable for storage.
        """
        return self._fernet.encrypt(data)

    def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt Fernet-encrypted bytes.

        Args:
            encrypted_data: The encrypted bytes from storage.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data).
        """
        return self._fernet.decrypt(encrypted_data)

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key for production use.

        This static method generates a cryptographically secure Fernet key
        suitable for production environments. Store the generated key securely
        in environment variables or secrets management systems.

        Returns:
            Base64-encoded Fernet key as a string.

        Example:
            ```python
            # Generate a new key
            key = TokenEncryption.generate_key()

            # Store securely (example - use proper secrets management)
            print(f"Set this in your environment:")
            print(f"export FRAMEIO_AUTH_ENCRYPTION_KEY='{key}'")

            # Use the key
            encryption = TokenEncryption(key=key)
            ```

        Warning:
            Never commit generated keys to source control. Always store in
            secure environment variables or secrets management systems.
        """
        return Fernet.generate_key().decode()
