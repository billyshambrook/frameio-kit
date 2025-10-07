"""Middleware system for adding cross-cutting concerns to Frame.io integrations.

This module provides a powerful way to add cross-cutting concerns to your Frame.io
integration without cluttering your handler functions. You can use middleware for
logging, authentication, metrics collection, error handling, and more.

The middleware system follows a chain-of-responsibility pattern. When an event is
received, it flows through each middleware in the order they were registered, then
to your handler, and finally back through the middleware in reverse order.
"""

from typing import Awaitable, Callable

from .events import ActionEvent, AnyEvent, WebhookEvent
from .ui import AnyResponse

NextFunc = Callable[[AnyEvent], Awaitable[AnyResponse]]
"""Type alias for the next function in the middleware chain."""


class Middleware:
    """Base class for creating middleware in Frame.io integrations.

    Middleware provides a powerful way to add cross-cutting concerns to your Frame.io
    integration without cluttering your handler functions. You can use middleware for
    logging, authentication, metrics collection, error handling, and more.

    The `Middleware` base class provides three hooks you can override:

    - `__call__`: The main entry point that runs for every event (both webhooks and actions)
    - `on_webhook`: Runs only for webhook events
    - `on_action`: Runs only for custom action events

    Example:
        ```python
        class TimingMiddleware(Middleware):
            async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
                start_time = time.monotonic()
                response = await next(event)
                duration = time.monotonic() - start_time
                print(f"Processed {event.type} in {duration:.2f}s")
                return response

        app = App(middleware=[TimingMiddleware()])
        ```
    """

    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        """
        The main entry point that runs for **every event** (both webhooks and actions).
        This is where you implement logic that should apply universally.


        Override this method when you need logic that should run on every single event,
        regardless of its type. This is perfect for universal concerns like:

        - Request timing and performance monitoring
        - Error handling and logging
        - Authentication and authorization
        - Request/response transformation

        Args:
            event: The event being processed (WebhookEvent or ActionEvent)
            next: Function to call the next middleware or handler in the chain

        Returns:
            The response from the next middleware or handler, or None

        Example:
            ```python
            async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
                # Code here runs before every event
                result = await next(event)  # Call the next middleware or handler
                # Code here runs after every event
                return result
            ```

        Note:
            When you override `__call__`, you completely replace the base implementation.
            This means:
            - Without `super()`: The `on_webhook` and `on_action` methods will not be called
            - With `super()`: The original dispatch logic is preserved, so `on_webhook` and `on_action` will still be called
        """
        if isinstance(event, WebhookEvent):
            return await self.on_webhook(event, next)
        elif isinstance(event, ActionEvent):
            return await self.on_action(event, next)
        return await next(event)

    async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
        """Runs only for webhook events.

        Override this method when you need webhook-specific logic that doesn't apply to custom actions.

        Args:
            event: The webhook event being processed
            next: Function to call the next middleware or handler in the chain

        Returns:
            The response from the next middleware or handler, or None

        Example:
            ```python
            async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
                # Code here runs only for webhook events
                result = await next(event)
                return result
            ```
        """
        return await next(event)

    async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
        """Runs only for custom action events.

        Override this method when you need action-specific logic that doesn't apply to webhooks.

        Args:
            event: The action event being processed
            next: Function to call the next middleware or handler in the chain

        Returns:
            The response from the next middleware or handler, or None

        Example:
            ```python
            async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
                # Code here runs only for action events
                result = await next(event)
                return result
            ```
        """
        return await next(event)
