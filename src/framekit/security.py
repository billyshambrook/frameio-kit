import hashlib
import hmac
import time

from starlette.datastructures import Headers

# Per Frame.io documentation, we should reject timestamps older than 5 minutes.
TIMESTAMP_TOLERANCE_SECONDS = 300


async def verify_signature(headers: Headers, body: bytes, secret: str) -> bool:
    """
    Verifies the HMAC-SHA256 signature of an incoming Frame.io request.

    This function is a critical security utility for validating that a webhook
    or custom action request genuinely originated from Frame.io and that its
    payload has not been tampered with. It should be called at the beginning
    of any request handler that receives events from Frame.io.

    It validates the request by checking the timestamp to prevent replay attacks
    and by computing an HMAC-SHA256 signature from the request body and your
    unique secret, comparing it securely to the signature provided in the header.

    Args:
        headers: The incoming request headers, obtained directly from your web
            framework's request object (e.g., `request.headers`). This function
            expects to find 'X-Frameio-Request-Timestamp' and
            'X-Frameio-Signature' headers.
        body: The raw, unmodified request body as bytes, obtained directly
            from your web framework's request object (e.g., `await request.body()`).
            It is crucial that this is the raw body, not a parsed JSON object.
        secret: The unique signing secret provided by Frame.io when you
            created the webhook or custom action. It's recommended to store this
            securely (e.g., as an environment variable).

    Returns:
        True if the signature is valid and the request is authentic.
        False if the signature is invalid, the timestamp is too old, or
        required headers are missing.
    """
    try:
        req_timestamp_str = headers["X-Frameio-Request-Timestamp"]
        req_signature = headers["X-Frameio-Signature"]
    except KeyError:
        return False  # Missing required headers

    # 1. Verify timestamp to prevent replay attacks
    current_time = time.time()
    if (current_time - int(req_timestamp_str)) > TIMESTAMP_TOLERANCE_SECONDS:
        return False

    # 2. Compute the expected signature
    message = f"v0:{req_timestamp_str}:".encode("latin-1") + body
    computed_hash = hmac.new(secret.encode("latin-1"), msg=message, digestmod=hashlib.sha256).hexdigest()
    expected_signature = f"v0={computed_hash}"

    # 3. Compare signatures securely
    return hmac.compare_digest(req_signature, expected_signature)
