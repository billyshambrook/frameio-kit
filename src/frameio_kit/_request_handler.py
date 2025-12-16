"""Request handling utilities for Frame.io Kit.

This module provides functions for parsing, validating, and verifying
incoming requests from Frame.io webhooks and custom actions.
"""

import json
import logging
from typing import Any

from pydantic import ValidationError
from starlette.datastructures import Headers

from ._events import AnyEvent
from ._exceptions import EventValidationError, SignatureVerificationError
from ._security import verify_signature

logger = logging.getLogger(__name__)


class ParsedRequest:
    """Container for parsed request data.

    Attributes:
        payload: The parsed JSON payload.
        event_type: The event type from the payload.
        timestamp: The request timestamp from headers.
    """

    def __init__(self, payload: dict[str, Any], event_type: str, timestamp: int) -> None:
        self.payload = payload
        self.event_type = event_type
        self.timestamp = timestamp


def parse_request_body(body: bytes) -> dict[str, Any]:
    """Parse JSON request body.

    Args:
        body: Raw request body bytes.

    Returns:
        Parsed JSON payload as a dictionary.

    Raises:
        ValueError: If the body is not valid JSON.
    """
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        return payload
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e


def extract_event_type(payload: dict[str, Any]) -> str:
    """Extract event type from payload.

    Args:
        payload: Parsed JSON payload.

    Returns:
        The event type string.

    Raises:
        ValueError: If event type is missing or empty.
    """
    event_type = payload.get("type")
    if not event_type:
        raise ValueError("Payload missing 'type' field")
    return event_type


def extract_timestamp(headers: Headers) -> int:
    """Extract and validate timestamp from request headers.

    Args:
        headers: Request headers.

    Returns:
        The timestamp as an integer.

    Raises:
        ValueError: If timestamp header is missing or invalid.
    """
    try:
        timestamp_str = headers["X-Frameio-Request-Timestamp"]
        return int(timestamp_str)
    except KeyError:
        raise ValueError("Missing X-Frameio-Request-Timestamp header")
    except ValueError:
        raise ValueError("Invalid X-Frameio-Request-Timestamp header format")


def parse_request(body: bytes, headers: Headers) -> ParsedRequest:
    """Parse and extract data from an incoming request.

    This function combines parsing the body, extracting the event type,
    and extracting the timestamp into a single operation.

    Args:
        body: Raw request body bytes.
        headers: Request headers.

    Returns:
        ParsedRequest containing payload, event type, and timestamp.

    Raises:
        ValueError: If parsing fails for any reason.
    """
    payload = parse_request_body(body)
    event_type = extract_event_type(payload)
    timestamp = extract_timestamp(headers)

    # Add timestamp to payload for event validation
    payload["timestamp"] = timestamp

    return ParsedRequest(payload=payload, event_type=event_type, timestamp=timestamp)


def validate_event(payload: dict[str, Any], model: type[AnyEvent]) -> AnyEvent:
    """Validate payload against an event model.

    Args:
        payload: Parsed JSON payload with timestamp added.
        model: Pydantic model class to validate against.

    Returns:
        Validated event instance.

    Raises:
        EventValidationError: If validation fails.
    """
    event_type = payload.get("type", "unknown")
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        raise EventValidationError(event_type, str(e)) from e


async def verify_request_signature(
    headers: Headers,
    body: bytes,
    secret: str,
) -> None:
    """Verify the request signature.

    Args:
        headers: Request headers containing signature.
        body: Raw request body bytes.
        secret: Secret for signature verification.

    Raises:
        SignatureVerificationError: If signature is invalid.
    """
    if not await verify_signature(headers, body, secret):
        raise SignatureVerificationError("Request signature verification failed")


class RequestHandler:
    """Orchestrates request parsing, validation, and verification.

    This class provides a high-level interface for handling incoming
    requests, combining all the steps into a single workflow.

    Example:
        ```python
        handler = RequestHandler()
        parsed = handler.parse(body, headers)
        event = handler.validate(parsed.payload, WebhookEvent)
        await handler.verify(headers, body, secret)
        ```
    """

    def parse(self, body: bytes, headers: Headers) -> ParsedRequest:
        """Parse an incoming request.

        Args:
            body: Raw request body bytes.
            headers: Request headers.

        Returns:
            ParsedRequest containing payload, event type, and timestamp.

        Raises:
            ValueError: If parsing fails.
        """
        return parse_request(body, headers)

    def validate(self, payload: dict[str, Any], model: type[AnyEvent]) -> AnyEvent:
        """Validate payload against an event model.

        Args:
            payload: Parsed JSON payload with timestamp.
            model: Event model class.

        Returns:
            Validated event instance.

        Raises:
            EventValidationError: If validation fails.
        """
        return validate_event(payload, model)

    async def verify(self, headers: Headers, body: bytes, secret: str) -> None:
        """Verify request signature.

        Args:
            headers: Request headers.
            body: Raw request body.
            secret: Signing secret.

        Raises:
            SignatureVerificationError: If verification fails.
        """
        await verify_request_signature(headers, body, secret)
