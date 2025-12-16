"""Secret resolution strategy for Frame.io webhooks and actions.

This module provides a centralized strategy for resolving secrets used
in signature verification. It supports multiple sources with a clear
precedence chain:

1. Decorator-level static secret
2. Decorator-level resolver function
3. App-level secret resolver protocol
4. Environment variable fallback
"""

import logging
import os
from typing import Awaitable, Callable, Protocol, cast

from ._events import ActionEvent, WebhookEvent
from ._exceptions import SecretResolutionError

logger = logging.getLogger(__name__)

# Type aliases for decorator-level secret resolvers
WebhookSecretResolver = Callable[[WebhookEvent], Awaitable[str]]
ActionSecretResolver = Callable[[ActionEvent], Awaitable[str]]


class SecretResolverProtocol(Protocol):
    """Protocol for app-level secret resolution.

    Implement this protocol to provide dynamic secret resolution for both
    webhooks and actions. Each method receives the specific event type it
    handles, allowing for context-aware secret lookup (e.g., from a database).

    Example:
        ```python
        class DatabaseSecretResolver:
            def __init__(self, db):
                self.db = db

            async def get_webhook_secret(self, event: WebhookEvent) -> str:
                return await self.db.webhooks.get_secret(event.account_id)

            async def get_action_secret(self, event: ActionEvent) -> str:
                return await self.db.actions.get_secret(event.resource.id)

        resolver = DatabaseSecretResolver(db)
        app = App(secret_resolver=resolver)
        ```
    """

    async def get_webhook_secret(self, event: WebhookEvent) -> str:
        """Resolve secret for webhook events.

        Args:
            event: The webhook event being processed.

        Returns:
            The secret to use for signature verification.
        """
        ...

    async def get_action_secret(self, event: ActionEvent) -> str:
        """Resolve secret for action events.

        Args:
            event: The action event being processed.

        Returns:
            The secret to use for signature verification.
        """
        ...


class SecretResolutionStrategy:
    """Centralized secret resolution for webhooks and actions.

    This class encapsulates the logic for resolving secrets from various
    sources, implementing a clear precedence chain.

    Attributes:
        static_secret: Optional static secret string.
        decorator_resolver: Optional decorator-level resolver function.
        app_resolver: Optional app-level resolver implementing SecretResolverProtocol.
    """

    def __init__(
        self,
        static_secret: str | None = None,
        decorator_resolver: WebhookSecretResolver | ActionSecretResolver | None = None,
        app_resolver: SecretResolverProtocol | None = None,
    ) -> None:
        """Initialize the secret resolution strategy.

        Args:
            static_secret: Static secret string from decorator.
            decorator_resolver: Callable resolver from decorator.
            app_resolver: App-level resolver implementing the protocol.
        """
        self.static_secret = static_secret
        self.decorator_resolver = decorator_resolver
        self.app_resolver = app_resolver

    async def resolve(self, event: WebhookEvent | ActionEvent) -> str:
        """Resolve the secret for the given event.

        Implements the precedence chain:
        1. Static secret from decorator
        2. Decorator-level resolver
        3. App-level resolver

        Args:
            event: The event to resolve the secret for.

        Returns:
            The resolved secret string.

        Raises:
            SecretResolutionError: If no secret can be resolved or resolution fails.
        """
        event_type = event.type

        # 1. Static secret from decorator
        if self.static_secret:
            return self.static_secret

        # 2. Decorator-level resolver
        if self.decorator_resolver:
            try:
                if isinstance(event, WebhookEvent):
                    webhook_resolver = cast(WebhookSecretResolver, self.decorator_resolver)
                    secret = await webhook_resolver(event)
                else:
                    action_resolver = cast(ActionSecretResolver, self.decorator_resolver)
                    secret = await action_resolver(event)

                if not secret:
                    raise SecretResolutionError(event_type, "Decorator resolver returned empty value")
                return secret
            except SecretResolutionError:
                raise
            except Exception as e:
                logger.exception("Error resolving secret with decorator resolver")
                raise SecretResolutionError(event_type, f"Decorator resolver failed: {e}") from e

        # 3. App-level resolver
        if self.app_resolver:
            try:
                if isinstance(event, WebhookEvent):
                    secret = await self.app_resolver.get_webhook_secret(event)
                else:
                    secret = await self.app_resolver.get_action_secret(event)

                if not secret:
                    raise SecretResolutionError(event_type, "App resolver returned empty value")
                return secret
            except SecretResolutionError:
                raise
            except Exception as e:
                logger.exception("Error resolving secret with app-level resolver")
                raise SecretResolutionError(event_type, f"App resolver failed: {e}") from e

        # No secret source available
        raise SecretResolutionError(event_type, "No secret source configured")


def resolve_secret_at_decorator_time(
    secret: str | WebhookSecretResolver | ActionSecretResolver | None,
    env_var_name: str,
    handler_type: str,
    app_resolver: SecretResolverProtocol | None = None,
) -> tuple[str | None, WebhookSecretResolver | ActionSecretResolver | None]:
    """Resolve secret configuration at decorator registration time.

    Implements the precedence chain:
    1. Explicit secret parameter (non-empty string or resolver callable)
    2. App-level secret resolver (if configured)
    3. Environment variable
    4. Fail with ValueError

    Args:
        secret: Secret string, resolver callable, or None.
        env_var_name: Name of environment variable to fall back to
            (e.g., "WEBHOOK_SECRET").
        handler_type: Type of handler for error messages
            (e.g., "Webhook", "Custom action").
        app_resolver: Optional app-level resolver.

    Returns:
        Tuple of (static_secret, decorator_resolver):
        - static_secret: String to use for signature verification, or None
          if using a resolver.
        - decorator_resolver: Callable resolver function, or None if using
          static secret or app-level resolver.

    Raises:
        ValueError: If no secret source is available.
    """
    if secret is not None:
        if isinstance(secret, str):
            if secret:  # Non-empty string
                # Explicit static secret provided
                return (secret, None)
            # Empty string falls through to app resolver / env var
        else:
            # Decorator-level resolver provided
            return (None, secret)

    # secret is None or empty string - check app resolver
    if app_resolver is not None:
        # Use app-level resolver (resolved at request time)
        return (None, None)

    # Fall back to environment variable
    resolved_secret = os.getenv(env_var_name)
    if not resolved_secret:
        raise ValueError(
            f"{handler_type} secret must be provided either via 'secret' parameter, "
            f"app-level secret_resolver, or {env_var_name} environment variable"
        )
    return (resolved_secret, None)
