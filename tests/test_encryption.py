"""Unit tests for token encryption functionality."""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

from frameio_kit._encryption import TokenEncryption


@pytest.fixture
def encryption_key() -> str:
    """Generate a test encryption key."""
    return TokenEncryption.generate_key()


class TestTokenEncryption:
    """Test suite for TokenEncryption class."""

    def test_encrypt_decrypt_round_trip(self, encryption_key: str):
        """Test that encrypting and decrypting returns the same data."""
        encryption = TokenEncryption(key=encryption_key)
        plaintext = b"hello world"

        encrypted = encryption.encrypt(plaintext)
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 0

        decrypted = encryption.decrypt(encrypted)
        assert decrypted == plaintext

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

    def test_invalid_key_raises_exception(self):
        """Test that providing an invalid key raises an exception."""
        with pytest.raises(Exception):
            TokenEncryption(key="invalid_key_not_base64")

    def test_decrypt_with_wrong_key_raises_exception(self):
        """Test that decrypting with a different key fails."""
        encryption1 = TokenEncryption(key=TokenEncryption.generate_key())
        encryption2 = TokenEncryption(key=TokenEncryption.generate_key())

        encrypted = encryption1.encrypt(b"secret")

        with pytest.raises(InvalidToken):
            encryption2.decrypt(encrypted)

    def test_decrypt_corrupted_data_raises_exception(self, encryption_key: str):
        """Test that decrypting corrupted data raises an exception."""
        encryption = TokenEncryption(key=encryption_key)

        with pytest.raises(InvalidToken):
            encryption.decrypt(b"corrupted_encrypted_data_not_valid")

    def test_key_from_environment_variable(self, encryption_key: str):
        """Test that encryption key is loaded from environment variable."""
        with patch.dict(os.environ, {"FRAMEIO_AUTH_ENCRYPTION_KEY": encryption_key}):
            encryption = TokenEncryption()

            encrypted = encryption.encrypt(b"env test")
            assert encryption.decrypt(encrypted) == b"env test"

    def test_ephemeral_key_generation_with_warning(self, caplog):
        """Test that ephemeral key is generated with warning when no key configured."""
        import logging

        with patch.dict(os.environ, {}, clear=True):
            with caplog.at_level(logging.WARNING, logger="frameio_kit._encryption"):
                encryption = TokenEncryption()

                encrypted = encryption.encrypt(b"ephemeral test")
                assert encryption.decrypt(encrypted) == b"ephemeral test"

            assert "ephemeral key" in caplog.text.lower()

    def test_encrypt_different_data_produces_different_output(self, encryption_key: str):
        """Test that encrypting different data produces different encrypted output."""
        encryption = TokenEncryption(key=encryption_key)

        encrypted1 = encryption.encrypt(b"data one")
        encrypted2 = encryption.encrypt(b"data two")

        assert encrypted1 != encrypted2

    def test_same_data_encrypted_twice_produces_different_output(self, encryption_key: str):
        """Test that Fernet produces different output for same input (nonce randomization)."""
        encryption = TokenEncryption(key=encryption_key)
        plaintext = b"same data"

        encrypted1 = encryption.encrypt(plaintext)
        encrypted2 = encryption.encrypt(plaintext)

        # Fernet includes a random nonce, so same data encrypted twice differs
        assert encrypted1 != encrypted2

        # But both should decrypt to the same data
        assert encryption.decrypt(encrypted1) == encryption.decrypt(encrypted2) == plaintext

    def test_explicit_key_takes_precedence_over_environment(self):
        """Test that explicit key parameter takes precedence over environment variable."""
        env_key = TokenEncryption.generate_key()
        explicit_key = TokenEncryption.generate_key()

        with patch.dict(os.environ, {"FRAMEIO_AUTH_ENCRYPTION_KEY": env_key}):
            encryption = TokenEncryption(key=explicit_key)

            encrypted = encryption.encrypt(b"precedence test")

            # Should NOT be decryptable with env key
            env_encryption = TokenEncryption(key=env_key)
            with pytest.raises(InvalidToken):
                env_encryption.decrypt(encrypted)

            # Should be decryptable with explicit key
            explicit_encryption = TokenEncryption(key=explicit_key)
            assert explicit_encryption.decrypt(encrypted) == b"precedence test"
