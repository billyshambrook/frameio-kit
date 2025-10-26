"""Unit tests for token encryption functionality."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

from frameio_kit._encryption import TokenEncryption
from frameio_kit._storage import TokenData


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
def encryption_key() -> str:
    """Generate a test encryption key."""
    return TokenEncryption.generate_key()


class TestTokenEncryption:
    """Test suite for TokenEncryption class."""

    def test_encrypt_decrypt_round_trip(self, sample_token_data: TokenData, encryption_key: str):
        """Test that encrypting and decrypting returns the same data."""
        encryption = TokenEncryption(key=encryption_key)

        # Encrypt
        encrypted = encryption.encrypt(sample_token_data)
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 0

        # Decrypt
        decrypted = encryption.decrypt(encrypted)

        # Verify all fields match
        assert decrypted.access_token == sample_token_data.access_token
        assert decrypted.refresh_token == sample_token_data.refresh_token
        assert decrypted.expires_at == sample_token_data.expires_at
        assert decrypted.scopes == sample_token_data.scopes
        assert decrypted.user_id == sample_token_data.user_id

    def test_generate_key_produces_valid_fernet_key(self):
        """Test that generate_key() produces a valid Fernet key."""
        key = TokenEncryption.generate_key()

        # Key should be a string
        assert isinstance(key, str)

        # Key should be base64-encoded (44 characters for Fernet)
        assert len(key) == 44

        # Key should be usable with Fernet
        fernet = Fernet(key.encode())
        test_data = b"test data"
        encrypted = fernet.encrypt(test_data)
        decrypted = fernet.decrypt(encrypted)
        assert decrypted == test_data

    def test_invalid_key_raises_exception(self, sample_token_data: TokenData):
        """Test that providing an invalid key raises an exception."""
        with pytest.raises(Exception):
            TokenEncryption(key="invalid_key_not_base64")

    def test_decrypt_with_wrong_key_raises_exception(self, sample_token_data: TokenData):
        """Test that decrypting with a different key fails."""
        encryption1 = TokenEncryption(key=TokenEncryption.generate_key())
        encryption2 = TokenEncryption(key=TokenEncryption.generate_key())

        encrypted = encryption1.encrypt(sample_token_data)

        with pytest.raises(InvalidToken):
            encryption2.decrypt(encrypted)

    def test_decrypt_corrupted_data_raises_exception(self, encryption_key: str):
        """Test that decrypting corrupted data raises an exception."""
        encryption = TokenEncryption(key=encryption_key)

        corrupted_data = b"corrupted_encrypted_data_not_valid"

        with pytest.raises(InvalidToken):
            encryption.decrypt(corrupted_data)

    def test_key_from_environment_variable(self, sample_token_data: TokenData, encryption_key: str):
        """Test that encryption key is loaded from environment variable."""
        with patch.dict(os.environ, {"FRAMEIO_AUTH_ENCRYPTION_KEY": encryption_key}):
            encryption = TokenEncryption()

            # Should be able to encrypt/decrypt
            encrypted = encryption.encrypt(sample_token_data)
            decrypted = encryption.decrypt(encrypted)

            assert decrypted.user_id == sample_token_data.user_id

    def test_ephemeral_key_generation_with_warning_when_no_keyring(self, sample_token_data: TokenData):
        """Test that ephemeral key is generated with warning when keyring unavailable."""
        with patch.dict(os.environ, {}, clear=True):  # Clear all env vars
            # Make keyring unavailable by removing it from sys.modules
            import sys

            original_modules = sys.modules.copy()
            if "keyring" in sys.modules:
                del sys.modules["keyring"]

            try:
                with pytest.warns(UserWarning, match="Using ephemeral key"):
                    encryption = TokenEncryption()

                    # Should still work, just with ephemeral key
                    encrypted = encryption.encrypt(sample_token_data)
                    decrypted = encryption.decrypt(encrypted)

                    assert decrypted.user_id == sample_token_data.user_id
            finally:
                # Restore sys.modules
                sys.modules.update(original_modules)

    def test_keyring_integration(self, sample_token_data: TokenData):
        """Test keyring integration for key storage (if keyring available)."""
        with patch.dict(os.environ, {}, clear=True):  # Clear env vars
            # Mock keyring module
            mock_keyring = MagicMock()
            test_key = TokenEncryption.generate_key()
            mock_keyring.get_password.return_value = test_key

            with patch.dict("sys.modules", {"keyring": mock_keyring}):
                encryption = TokenEncryption()

                # Should have retrieved key from keyring
                mock_keyring.get_password.assert_called_once_with("frameio-kit", "auth-encryption-key")

                # Should work for encryption/decryption
                encrypted = encryption.encrypt(sample_token_data)
                decrypted = encryption.decrypt(encrypted)

                assert decrypted.user_id == sample_token_data.user_id

    def test_keyring_creates_new_key_if_none_exists(self, sample_token_data: TokenData):
        """Test that keyring creates and stores a new key if none exists."""
        with patch.dict(os.environ, {}, clear=True):  # Clear env vars
            # Mock keyring module with no existing key
            mock_keyring = MagicMock()
            mock_keyring.get_password.return_value = None

            with patch.dict("sys.modules", {"keyring": mock_keyring}):
                encryption = TokenEncryption()

                # Should have tried to get key
                mock_keyring.get_password.assert_called_once_with("frameio-kit", "auth-encryption-key")

                # Should have generated new key and stored it
                # We can't easily mock Fernet.generate_key, but we can verify set_password was called
                assert mock_keyring.set_password.called
                call_args = mock_keyring.set_password.call_args
                assert call_args[0][0] == "frameio-kit"
                assert call_args[0][1] == "auth-encryption-key"
                # Third argument should be a valid base64 string (44 chars for Fernet)
                assert len(call_args[0][2]) == 44

                # Verify encryption still works
                encrypted = encryption.encrypt(sample_token_data)
                decrypted = encryption.decrypt(encrypted)
                assert decrypted.user_id == sample_token_data.user_id

    def test_keyring_failure_falls_back_to_ephemeral(self, sample_token_data: TokenData):
        """Test that keyring failure falls back to ephemeral key with warning."""
        with patch.dict(os.environ, {}, clear=True):  # Clear env vars
            # Mock keyring to raise exception
            mock_keyring = MagicMock()
            mock_keyring.get_password.side_effect = Exception("Keyring access denied")

            with patch.dict("sys.modules", {"keyring": mock_keyring}):
                with pytest.warns(UserWarning, match="Failed to access system keyring"):
                    encryption = TokenEncryption()

                    # Should still work with ephemeral key
                    encrypted = encryption.encrypt(sample_token_data)
                    decrypted = encryption.decrypt(encrypted)

                    assert decrypted.user_id == sample_token_data.user_id

    def test_encrypt_different_data_produces_different_output(self, encryption_key: str):
        """Test that encrypting different TokenData produces different encrypted output."""
        encryption = TokenEncryption(key=encryption_key)

        token1 = TokenData(
            access_token="token1",
            refresh_token="refresh1",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["scope1"],
            user_id="user1",
        )

        token2 = TokenData(
            access_token="token2",
            refresh_token="refresh2",
            expires_at=datetime.now() + timedelta(hours=2),
            scopes=["scope2"],
            user_id="user2",
        )

        encrypted1 = encryption.encrypt(token1)
        encrypted2 = encryption.encrypt(token2)

        # Different data should produce different encrypted bytes
        assert encrypted1 != encrypted2

    def test_same_data_encrypted_twice_produces_different_output(
        self, sample_token_data: TokenData, encryption_key: str
    ):
        """Test that Fernet produces different output for same input (nonce randomization)."""
        encryption = TokenEncryption(key=encryption_key)

        encrypted1 = encryption.encrypt(sample_token_data)
        encrypted2 = encryption.encrypt(sample_token_data)

        # Fernet includes a random nonce, so same data encrypted twice differs
        assert encrypted1 != encrypted2

        # But both should decrypt to the same data
        decrypted1 = encryption.decrypt(encrypted1)
        decrypted2 = encryption.decrypt(encrypted2)

        assert decrypted1.user_id == decrypted2.user_id == sample_token_data.user_id

    def test_explicit_key_takes_precedence_over_environment(self, sample_token_data: TokenData):
        """Test that explicit key parameter takes precedence over environment variable."""
        env_key = TokenEncryption.generate_key()
        explicit_key = TokenEncryption.generate_key()

        with patch.dict(os.environ, {"FRAMEIO_AUTH_ENCRYPTION_KEY": env_key}):
            encryption = TokenEncryption(key=explicit_key)

            # Encrypt with explicit key
            encrypted = encryption.encrypt(sample_token_data)

            # Should NOT be decryptable with env key
            env_encryption = TokenEncryption(key=env_key)
            with pytest.raises(InvalidToken):
                env_encryption.decrypt(encrypted)

            # Should be decryptable with explicit key
            explicit_encryption = TokenEncryption(key=explicit_key)
            decrypted = explicit_encryption.decrypt(encrypted)
            assert decrypted.user_id == sample_token_data.user_id
