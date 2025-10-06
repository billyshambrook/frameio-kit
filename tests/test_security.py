import time

import pytest
from starlette.datastructures import Headers

from frameio_kit.security import TIMESTAMP_TOLERANCE_SECONDS, verify_signature


@pytest.fixture
def sample_secret() -> str:
    """A sample secret key for testing."""
    return "my_super_secret_string_for_testing"


@pytest.fixture
def sample_body() -> bytes:
    """A sample request body for testing."""
    return b'{"type":"file.ready","resource":{"id":"file_id_123"}}'


async def test_verify_signature_succeeds_with_valid_signature(sample_body, sample_secret, create_valid_signature):
    """
    Tests that the signature verification passes for a perfectly valid request.
    This is the "happy path".
    """
    current_time = int(time.time())
    signature = create_valid_signature(current_time, sample_body, sample_secret)

    headers = Headers(
        {
            "X-Frameio-Request-Timestamp": str(current_time),
            "X-Frameio-Signature": signature,
        }
    )

    is_valid = await verify_signature(headers, sample_body, sample_secret)
    assert is_valid is True


async def test_verify_signature_fails_with_missing_signature_header(sample_body, sample_secret):
    """
    Tests that verification fails if the signature header is missing.
    """
    headers = Headers({"X-Frameio-Request-Timestamp": str(int(time.time()))})
    is_valid = await verify_signature(headers, sample_body, sample_secret)
    assert is_valid is False


async def test_verify_signature_fails_with_missing_timestamp_header(sample_body, sample_secret):
    """
    Tests that verification fails if the timestamp header is missing.
    """
    headers = Headers({"X-Frameio-Signature": "v0=somesignature"})
    is_valid = await verify_signature(headers, sample_body, sample_secret)
    assert is_valid is False


async def test_verify_signature_fails_with_expired_timestamp(sample_body, sample_secret, create_valid_signature):
    """
    Tests that verification fails if the timestamp is too old (replay attack).
    """
    expired_time = int(time.time()) - (TIMESTAMP_TOLERANCE_SECONDS + 1)
    signature = create_valid_signature(expired_time, sample_body, sample_secret)

    headers = Headers({"X-Frameio-Request-Timestamp": str(expired_time), "X-Frameio-Signature": signature})

    is_valid = await verify_signature(headers, sample_body, sample_secret)
    assert is_valid is False


async def test_verify_signature_fails_with_tampered_body(sample_body, sample_secret, create_valid_signature):
    """
    Tests that verification fails if the request body has been altered.
    """
    current_time = int(time.time())
    # Signature is created for the original body
    signature = create_valid_signature(current_time, sample_body, sample_secret)

    headers = Headers({"X-Frameio-Request-Timestamp": str(current_time), "X-Frameio-Signature": signature})

    # But the function receives a different, tampered body
    tampered_body = b'{"type":"file.deleted","resource":{"id":"file_id_456"}}'

    is_valid = await verify_signature(headers, tampered_body, sample_secret)
    assert is_valid is False


async def test_verify_signature_fails_with_wrong_secret(sample_body, sample_secret, create_valid_signature) -> None:
    """
    Tests that verification fails if the wrong secret is used.
    """
    current_time = int(time.time())
    signature = create_valid_signature(current_time, sample_body, sample_secret)

    headers = Headers({"X-Frameio-Request-Timestamp": str(current_time), "X-Frameio-Signature": signature})

    wrong_secret = "this_is_not_the_correct_secret"
    is_valid = await verify_signature(headers, sample_body, wrong_secret)
    assert is_valid is False


async def test_verify_signature_succeeds_with_empty_body(sample_secret, create_valid_signature) -> None:
    """
    Tests that signature verification works correctly even with an empty body.
    """
    current_time = int(time.time())
    empty_body = b""
    signature = create_valid_signature(current_time, empty_body, sample_secret)

    headers = Headers({"X-Frameio-Request-Timestamp": str(current_time), "X-Frameio-Signature": signature})

    is_valid = await verify_signature(headers, empty_body, sample_secret)
    assert is_valid is True
