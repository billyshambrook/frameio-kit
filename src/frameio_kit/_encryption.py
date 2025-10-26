"""Token encryption utilities for secure OAuth token storage.

This module provides Fernet symmetric encryption for protecting OAuth tokens at rest.
Encryption keys can be provided explicitly, loaded from environment variables,
retrieved from the system keyring (development), or generated ephemerally with warnings.
"""

import os
import warnings

from cryptography.fernet import Fernet

from ._storage import TokenData


class TokenEncryption:
    """Encrypts and decrypts OAuth tokens using Fernet symmetric encryption.

    This class provides secure encryption/decryption of TokenData objects for
    storage. It supports multiple key sources with a clear hierarchy to balance
    security and developer experience.

    Key Loading Hierarchy:
        1. Explicit key parameter (highest priority)
        2. FRAMEIO_AUTH_ENCRYPTION_KEY environment variable
        3. System keyring (development only, requires keyring package)
        4. Ephemeral key generation with warning (lowest priority)

    Attributes:
        _key: The Fernet encryption key (bytes).
        _fernet: The Fernet encryption instance.

    Example:
        ```python
        # Production: Use environment variable
        os.environ["FRAMEIO_AUTH_ENCRYPTION_KEY"] = TokenEncryption.generate_key()
        encryption = TokenEncryption()

        # Encrypt token data
        token_data = TokenData(...)
        encrypted_bytes = encryption.encrypt(token_data)

        # Decrypt token data
        decrypted_token = encryption.decrypt(encrypted_bytes)
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
        3. System keyring (development only)
        4. Generated ephemerally with warning

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
            # Development: Try to use system keyring, else ephemeral
            self._key = self._get_or_create_dev_key()

        self._fernet = Fernet(self._key)

    def _get_or_create_dev_key(self) -> bytes:
        """Get encryption key from system keyring or create ephemeral one.

        This method attempts to use the system keyring for persistent key storage
        during development. If keyring is unavailable or fails, it generates an
        ephemeral key and warns the developer.

        Returns:
            Fernet encryption key as bytes.

        Warning:
            Ephemeral keys are only stored in memory and will be lost on restart,
            causing all stored tokens to become inaccessible.
        """
        try:
            import keyring

            key = keyring.get_password("frameio-kit", "auth-encryption-key")
            if key:
                return key.encode()

            # Create and store new key in keyring
            key_bytes = Fernet.generate_key()
            keyring.set_password("frameio-kit", "auth-encryption-key", key_bytes.decode())
            return key_bytes
        except ImportError:
            # Keyring not available - use ephemeral key
            warnings.warn(
                "No encryption key configured and keyring unavailable. "
                "Using ephemeral key - tokens will be lost on restart. "
                "Set FRAMEIO_AUTH_ENCRYPTION_KEY in production.",
                UserWarning,
                stacklevel=3,
            )
            return Fernet.generate_key()
        except Exception:
            # Keyring failed - use ephemeral key
            warnings.warn(
                "Failed to access system keyring. "
                "Using ephemeral key - tokens will be lost on restart. "
                "Set FRAMEIO_AUTH_ENCRYPTION_KEY in production.",
                UserWarning,
                stacklevel=3,
            )
            return Fernet.generate_key()

    def encrypt(self, token_data: TokenData) -> bytes:
        """Encrypt token data to bytes for secure storage.

        Serializes the TokenData to JSON and encrypts it using Fernet symmetric
        encryption. The resulting bytes can be safely stored in any backend.

        Args:
            token_data: The TokenData object to encrypt.

        Returns:
            Encrypted bytes suitable for storage.

        Raises:
            Exception: If encryption fails (e.g., invalid Fernet key).

        Example:
            ```python
            token_data = TokenData(
                access_token="eyJhbGc...",
                refresh_token="def50200...",
                expires_at=datetime.now() + timedelta(hours=24),
                scopes=["openid", "AdobeID"],
                user_id="user_123"
            )

            encrypted = encryption.encrypt(token_data)
            # Store encrypted bytes in database, Redis, etc.
            await storage.set("user:123", encrypted)
            ```
        """
        json_data = token_data.model_dump_json()
        return self._fernet.encrypt(json_data.encode())

    def decrypt(self, encrypted_data: bytes) -> TokenData:
        """Decrypt bytes to TokenData object.

        Decrypts Fernet-encrypted bytes and deserializes the JSON to a TokenData
        object with full validation.

        Args:
            encrypted_data: The encrypted bytes from storage.

        Returns:
            Decrypted and validated TokenData object.

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data).
            pydantic.ValidationError: If the decrypted data is not valid TokenData.

        Example:
            ```python
            # Retrieve encrypted bytes from storage
            encrypted = await storage.get("user:123")

            if encrypted:
                token_data = encryption.decrypt(encrypted)
                print(f"Access token: {token_data.access_token}")
                print(f"Expires: {token_data.expires_at}")
            ```
        """
        decrypted = self._fernet.decrypt(encrypted_data)
        return TokenData.model_validate_json(decrypted)

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
