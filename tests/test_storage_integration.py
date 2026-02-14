"""Integration tests for storage backends with encryption.

These tests verify that storage implementations work correctly with
encrypted token data and support TTL expiration.
"""

import base64
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from frameio_kit._encryption import TokenEncryption
from frameio_kit._oauth import TokenData
from frameio_kit._storage import MemoryStorage, Storage


# Note: These helpers duplicate TokenManager._wrap_encrypted_bytes() and
# TokenManager._unwrap_encrypted_bytes() intentionally for test isolation.
# They allow testing storage integration without depending on TokenManager internals.


def _wrap_encrypted_bytes(encrypted_bytes: bytes) -> dict[str, str]:
    """Wrap encrypted bytes in dict format for storage."""
    return {"encrypted_token": base64.b64encode(encrypted_bytes).decode("utf-8")}


def _unwrap_encrypted_bytes(data: dict[str, str]) -> bytes:
    """Unwrap encrypted bytes from storage dict format."""
    return base64.b64decode(data["encrypted_token"])


@pytest.fixture
def sample_token_data() -> TokenData:
    """Create sample TokenData for testing."""
    return TokenData(
        access_token="test_access_token_abc123",
        refresh_token="test_refresh_token_xyz789",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        scopes=["openid", "AdobeID", "frameio.api"],
        user_id="user_test_123",
    )


@pytest.fixture
def encryption() -> TokenEncryption:
    """Create TokenEncryption instance for testing."""
    return TokenEncryption(key=TokenEncryption.generate_key())


@pytest.fixture
def memory_storage() -> MemoryStorage:
    """Create MemoryStorage instance for testing."""
    return MemoryStorage()


class TestProtocolConformance:
    """Test that implementations conform to the Storage protocol."""

    def test_memory_storage_is_storage(self):
        """Test that MemoryStorage satisfies the Storage protocol."""
        assert isinstance(MemoryStorage(), Storage)


class TestMemoryStorageIntegration:
    """Test suite for MemoryStorage integration with encryption."""

    async def test_basic_operations(
        self, memory_storage: MemoryStorage, encryption: TokenEncryption, sample_token_data: TokenData
    ):
        """Test that encrypted tokens can be stored and retrieved from MemoryStorage."""
        key = "user:test_123"

        # Encrypt token
        encrypted = encryption.encrypt(sample_token_data.model_dump_json().encode())
        wrapped = _wrap_encrypted_bytes(encrypted)

        # Store
        await memory_storage.put(key, wrapped)

        # Retrieve
        retrieved = await memory_storage.get(key)
        assert retrieved is not None

        # Decrypt and verify
        unwrapped = _unwrap_encrypted_bytes(retrieved)
        decrypted = TokenData.model_validate_json(encryption.decrypt(unwrapped))

        assert decrypted.user_id == sample_token_data.user_id
        assert decrypted.access_token == sample_token_data.access_token
        assert decrypted.refresh_token == sample_token_data.refresh_token

    async def test_multiple_users(self, memory_storage: MemoryStorage, encryption: TokenEncryption):
        """Test storing tokens for multiple users."""
        users = ["alice", "bob", "charlie"]

        # Store tokens for each user
        for user in users:
            token_data = TokenData(
                access_token=f"{user}_access",
                refresh_token=f"{user}_refresh",
                expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                scopes=["openid"],
                user_id=user,
            )
            encrypted = encryption.encrypt(token_data.model_dump_json().encode())
            wrapped = _wrap_encrypted_bytes(encrypted)
            await memory_storage.put(f"user:{user}", wrapped)

        # Retrieve and verify each token
        for user in users:
            retrieved = await memory_storage.get(f"user:{user}")
            assert retrieved is not None
            unwrapped = _unwrap_encrypted_bytes(retrieved)
            decrypted = TokenData.model_validate_json(encryption.decrypt(unwrapped))
            assert decrypted.access_token == f"{user}_access"

    async def test_ttl_expiration(self, memory_storage: MemoryStorage):
        """Test that entries expire after their TTL."""
        await memory_storage.put("key", {"data": "value"}, ttl=10)

        # Should exist before expiry
        assert await memory_storage.get("key") is not None

        # Advance monotonic time past TTL
        with patch("frameio_kit._storage.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + 11
            assert await memory_storage.get("key") is None

    async def test_no_ttl_does_not_expire(self, memory_storage: MemoryStorage):
        """Test that entries without TTL do not expire."""
        await memory_storage.put("key", {"data": "value"})

        with patch("frameio_kit._storage.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + 999999
            assert await memory_storage.get("key") is not None


class TestStorageBackendErrors:
    """Test error handling for storage backends."""

    async def test_get_nonexistent_key(self, memory_storage: MemoryStorage):
        """Test that getting a non-existent key returns None."""
        value = await memory_storage.get("user:nonexistent")
        assert value is None

    async def test_delete_nonexistent_key(self, memory_storage: MemoryStorage):
        """Test that deleting a non-existent key doesn't raise an error."""
        await memory_storage.delete("user:nonexistent")


class TestEncryptionWithStorage:
    """Test that encryption works correctly with storage backends."""

    async def test_different_keys_produce_different_encrypted_data(
        self, memory_storage: MemoryStorage, sample_token_data: TokenData
    ):
        """Test that the same data encrypted with different keys produces different ciphertext."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()

        encryption1 = TokenEncryption(key=key1)
        encryption2 = TokenEncryption(key=key2)

        # Encrypt with both keys
        token_bytes = sample_token_data.model_dump_json().encode()
        encrypted1 = encryption1.encrypt(token_bytes)
        encrypted2 = encryption2.encrypt(token_bytes)

        # Should be different
        assert encrypted1 != encrypted2

        # Store both
        wrapped1 = _wrap_encrypted_bytes(encrypted1)
        wrapped2 = _wrap_encrypted_bytes(encrypted2)

        await memory_storage.put("key1", wrapped1)
        await memory_storage.put("key2", wrapped2)

        # Retrieve and decrypt with correct keys
        retrieved1 = await memory_storage.get("key1")
        retrieved2 = await memory_storage.get("key2")

        assert retrieved1 is not None
        assert retrieved2 is not None

        unwrapped1 = _unwrap_encrypted_bytes(retrieved1)
        unwrapped2 = _unwrap_encrypted_bytes(retrieved2)

        decrypted1 = TokenData.model_validate_json(encryption1.decrypt(unwrapped1))
        decrypted2 = TokenData.model_validate_json(encryption2.decrypt(unwrapped2))

        # Both should decrypt to the same original data
        assert decrypted1.user_id == decrypted2.user_id == sample_token_data.user_id
