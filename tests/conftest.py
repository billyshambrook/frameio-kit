import hashlib
import hmac

import pytest


@pytest.fixture(scope="function")
def create_valid_signature():
    """Fixture to create a valid signature for testing."""

    def _create_valid_signature(timestamp: int, body: bytes, secret: str) -> str:
        """Helper function to generate a valid signature for testing."""
        message = f"v0:{timestamp}:".encode("latin-1") + body
        computed_hash = hmac.new(secret.encode("latin-1"), msg=message, digestmod=hashlib.sha256).hexdigest()
        return f"v0={computed_hash}"

    return _create_valid_signature
