"""Integration tests for storage backends with encryption.

These tests verify that py-key-value-aio stores can work with encrypted token data.
The tests use helper functions to wrap encrypted bytes in dict format as required
by py-key-value-aio stores.
"""

import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import pytest
from key_value.aio.stores.disk import DiskStore
from key_value.aio.stores.memory import MemoryStore

from frameio_kit._encryption import TokenEncryption
from frameio_kit._oauth import TokenData


# Note: These helpers duplicate TokenManager._wrap_encrypted_bytes() and
# TokenManager._unwrap_encrypted_bytes() intentionally for test isolation.
# They allow testing storage integration without depending on TokenManager internals.


def _wrap_encrypted_bytes(encrypted_bytes: bytes) -> dict[str, str]:
    """Wrap encrypted bytes in dict format for py-key-value-aio stores."""
    return {"encrypted_token": base64.b64encode(encrypted_bytes).decode("utf-8")}


def _unwrap_encrypted_bytes(data: dict[str, str]) -> bytes:
    """Unwrap encrypted bytes from py-key-value-aio dict format."""
    return base64.b64decode(data["encrypted_token"])


@pytest.fixture
def sample_token_data() -> TokenData:
    """Create sample TokenData for testing."""
    return TokenData(
        access_token="test_access_token_abc123",
        refresh_token="test_refresh_token_xyz789",
        expires_at=datetime.now() + timedelta(hours=24),
        scopes=["openid", "AdobeID", "frameio.api"],
        user_id="user_test_123",
    )


@pytest.fixture
def encryption() -> TokenEncryption:
    """Create TokenEncryption instance for testing."""
    return TokenEncryption(key=TokenEncryption.generate_key())


@pytest.fixture
async def memory_store() -> AsyncGenerator[MemoryStore, None]:
    """Create MemoryStore instance for testing."""
    store = MemoryStore()
    yield store
    # Cleanup
    await store.destroy()


@pytest.fixture
async def disk_store(tmp_path: Path) -> AsyncGenerator[DiskStore, None]:
    """Create DiskStore instance for testing."""
    store_path = tmp_path / "test_tokens"
    store = DiskStore(directory=str(store_path))
    yield store
    # DiskStore cleanup handled by tmp_path fixture


class TestMemoryStoreIntegration:
    """Test suite for MemoryStore integration with encryption."""

    async def test_basic_operations(
        self, memory_store: MemoryStore, encryption: TokenEncryption, sample_token_data: TokenData
    ):
        """Test that encrypted tokens can be stored and retrieved from MemoryStore."""
        key = "user:test_123"

        # Encrypt token
        encrypted = encryption.encrypt(sample_token_data)
        wrapped = _wrap_encrypted_bytes(encrypted)

        # Store
        await memory_store.put(key, wrapped)

        # Retrieve
        retrieved = await memory_store.get(key)
        assert retrieved is not None

        # Decrypt and verify
        unwrapped = _unwrap_encrypted_bytes(retrieved)
        decrypted = encryption.decrypt(unwrapped)

        assert decrypted.user_id == sample_token_data.user_id
        assert decrypted.access_token == sample_token_data.access_token
        assert decrypted.refresh_token == sample_token_data.refresh_token

    async def test_multiple_users(self, memory_store: MemoryStore, encryption: TokenEncryption):
        """Test storing tokens for multiple users."""
        users = ["alice", "bob", "charlie"]

        # Store tokens for each user
        for user in users:
            token_data = TokenData(
                access_token=f"{user}_access",
                refresh_token=f"{user}_refresh",
                expires_at=datetime.now() + timedelta(hours=1),
                scopes=["openid"],
                user_id=user,
            )
            encrypted = encryption.encrypt(token_data)
            wrapped = _wrap_encrypted_bytes(encrypted)
            await memory_store.put(f"user:{user}", wrapped)

        # Retrieve and verify each token
        for user in users:
            retrieved = await memory_store.get(f"user:{user}")
            assert retrieved is not None
            unwrapped = _unwrap_encrypted_bytes(retrieved)
            decrypted = encryption.decrypt(unwrapped)
            assert decrypted.access_token == f"{user}_access"


class TestDiskStoreIntegration:
    """Test suite for DiskStore integration with encryption."""

    async def test_basic_operations(
        self, disk_store: DiskStore, encryption: TokenEncryption, sample_token_data: TokenData
    ):
        """Test that encrypted tokens can be stored and retrieved from DiskStore."""
        key = "user:test_123"

        # Encrypt token
        encrypted = encryption.encrypt(sample_token_data)
        wrapped = _wrap_encrypted_bytes(encrypted)

        # Store
        await disk_store.put(key, wrapped)

        # Retrieve
        retrieved = await disk_store.get(key)
        assert retrieved is not None

        # Decrypt and verify
        unwrapped = _unwrap_encrypted_bytes(retrieved)
        decrypted = encryption.decrypt(unwrapped)

        assert decrypted.user_id == sample_token_data.user_id
        assert decrypted.access_token == sample_token_data.access_token

    async def test_persistence(self, tmp_path: Path, encryption: TokenEncryption, sample_token_data: TokenData):
        """Test that data persists across DiskStore instances."""
        store_path = tmp_path / "persistent_tokens"
        key = "user:persistent"

        # Create first store and save data
        store1 = DiskStore(directory=str(store_path))
        encrypted = encryption.encrypt(sample_token_data)
        wrapped = _wrap_encrypted_bytes(encrypted)
        await store1.put(key, wrapped)

        # Create second store pointing to same directory
        store2 = DiskStore(directory=str(store_path))
        retrieved = await store2.get(key)

        assert retrieved is not None
        unwrapped = _unwrap_encrypted_bytes(retrieved)
        decrypted = encryption.decrypt(unwrapped)
        assert decrypted.user_id == sample_token_data.user_id


class TestStorageBackendErrors:
    """Test error handling for storage backends."""

    async def test_get_nonexistent_key(self, memory_store: MemoryStore):
        """Test that getting a non-existent key returns None."""
        value = await memory_store.get("user:nonexistent")
        assert value is None

    async def test_delete_nonexistent_key(self, memory_store: MemoryStore):
        """Test that deleting a non-existent key doesn't raise an error."""
        # Should not raise
        await memory_store.delete("user:nonexistent")


class TestEncryptionWithStorage:
    """Test that encryption works correctly with storage backends."""

    async def test_different_keys_produce_different_encrypted_data(
        self, memory_store: MemoryStore, sample_token_data: TokenData
    ):
        """Test that the same data encrypted with different keys produces different ciphertext."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()

        encryption1 = TokenEncryption(key=key1)
        encryption2 = TokenEncryption(key=key2)

        # Encrypt with both keys
        encrypted1 = encryption1.encrypt(sample_token_data)
        encrypted2 = encryption2.encrypt(sample_token_data)

        # Should be different
        assert encrypted1 != encrypted2

        # Store both
        wrapped1 = _wrap_encrypted_bytes(encrypted1)
        wrapped2 = _wrap_encrypted_bytes(encrypted2)

        await memory_store.put("key1", wrapped1)
        await memory_store.put("key2", wrapped2)

        # Retrieve and decrypt with correct keys
        retrieved1 = await memory_store.get("key1")
        retrieved2 = await memory_store.get("key2")

        assert retrieved1 is not None
        assert retrieved2 is not None

        unwrapped1 = _unwrap_encrypted_bytes(retrieved1)
        unwrapped2 = _unwrap_encrypted_bytes(retrieved2)

        decrypted1 = encryption1.decrypt(unwrapped1)
        decrypted2 = encryption2.decrypt(unwrapped2)

        # Both should decrypt to the same original data
        assert decrypted1.user_id == decrypted2.user_id == sample_token_data.user_id
