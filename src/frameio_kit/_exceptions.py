"""Custom exception hierarchy for Frame.io Kit.

This module provides a structured exception hierarchy for handling errors
throughout the SDK. Using specific exception types allows for more precise
error handling and better error messages.
"""


class FrameioKitError(Exception):
    """Base exception for all Frame.io Kit errors.

    All exceptions raised by this library inherit from this base class,
    making it easy to catch any SDK-related error.

    Example:
        ```python
        try:
            await app.validate_configuration()
        except FrameioKitError as e:
            logger.error(f"SDK error: {e}")
        ```
    """

    pass


class SecretResolutionError(FrameioKitError):
    """Raised when secret resolution fails.

    This exception is raised when the secret for signature verification
    cannot be resolved from any source (decorator, app-level resolver,
    or environment variable).

    Attributes:
        event_type: The event type for which secret resolution failed.
        message: Descriptive error message.
    """

    def __init__(self, event_type: str, message: str | None = None) -> None:
        self.event_type = event_type
        self.message = message or f"Failed to resolve secret for event type '{event_type}'"
        super().__init__(self.message)


class SignatureVerificationError(FrameioKitError):
    """Raised when request signature verification fails.

    This exception indicates that the HMAC signature in the request
    headers does not match the expected signature, suggesting the
    request may have been tampered with or did not originate from Frame.io.
    """

    pass


class EventValidationError(FrameioKitError):
    """Raised when event payload validation fails.

    This exception wraps Pydantic validation errors to provide a
    consistent exception type for the SDK.

    Attributes:
        event_type: The event type that failed validation.
        validation_errors: Details about what fields failed validation.
    """

    def __init__(self, event_type: str, validation_errors: str) -> None:
        self.event_type = event_type
        self.validation_errors = validation_errors
        super().__init__(f"Validation failed for event '{event_type}': {validation_errors}")


class ConfigurationError(FrameioKitError):
    """Raised when application configuration is invalid.

    This exception is raised during startup validation when the
    application configuration is incomplete or inconsistent.

    Example:
        - Action requires user auth but OAuth not configured
        - No secret source available for a handler
    """

    pass


class OAuthError(FrameioKitError):
    """Base exception for OAuth-related errors."""

    pass


class TokenExchangeError(OAuthError):
    """Raised when OAuth token exchange fails.

    This can occur when:
    - The authorization code is invalid or expired
    - Required fields are missing from the token response
    - The token response contains invalid data
    """

    pass


class TokenRefreshError(OAuthError):
    """Raised when OAuth token refresh fails.

    This typically indicates the refresh token has been revoked or expired,
    requiring the user to re-authenticate.
    """

    pass


class InstallationError(FrameioKitError):
    """Base exception for installation-related errors."""

    pass


class InstallationNotFoundError(InstallationError):
    """No installation found for the given workspace."""

    pass
