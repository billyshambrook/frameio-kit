"""OpenTelemetry tracing middleware for Frame.io integrations.

This module provides automatic distributed tracing for incoming webhook and
custom action events. It creates a span for each event processed, recording
relevant attributes like event type, account ID, and resource ID.

The middleware requires the ``opentelemetry-api`` package, available via the
``otel`` extra::

    pip install frameio-kit[otel]

Example:
    ```python
    from frameio_kit import App, OpenTelemetryMiddleware

    app = App(middleware=[OpenTelemetryMiddleware()])
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._events import ActionEvent, AnyEvent
from ._middleware import Middleware, NextFunc
from ._responses import AnyResponse

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer, TracerProvider


class OpenTelemetryMiddleware(Middleware):
    """Middleware that creates OpenTelemetry spans for incoming Frame.io events.

    Each webhook or custom action event is wrapped in a span with attributes
    describing the event context. If the handler raises an exception, the error
    is recorded on the span before re-raising.

    When no OpenTelemetry SDK is configured, this middleware is a near-zero-cost
    no-op thanks to the ``opentelemetry-api`` package's built-in no-op tracer.

    Args:
        tracer_name: The name passed to ``trace.get_tracer()``. Defaults to
            ``"frameio_kit"``.
        tracer_provider: An optional ``TracerProvider`` instance. When ``None``
            (the default), the globally configured provider is used.

    Example:
        ```python
        from frameio_kit import App, OpenTelemetryMiddleware

        # Default tracer name, uses global provider
        app = App(middleware=[OpenTelemetryMiddleware()])

        # Custom tracer name
        app = App(middleware=[OpenTelemetryMiddleware(tracer_name="my_app")])
        ```
    """

    def __init__(self, tracer_name: str = "frameio_kit", tracer_provider: TracerProvider | None = None) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.trace import StatusCode
        except ImportError:
            raise ImportError(
                "opentelemetry-api is required for OpenTelemetryMiddleware. "
                "Install it with: pip install frameio-kit[otel]"
            ) from None

        self._tracer: Tracer = trace.get_tracer(tracer_name, tracer_provider=tracer_provider)
        self._span_kind = trace.SpanKind.SERVER
        self._status_ok = StatusCode.OK
        self._status_error = StatusCode.ERROR

    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        """Wrap event processing in an OpenTelemetry span.

        Args:
            event: The incoming webhook or action event.
            next: The next middleware or handler in the chain.

        Returns:
            The response from the next middleware or handler.
        """
        with self._tracer.start_as_current_span(
            f"frameio {event.type}",
            kind=self._span_kind,
            attributes={
                "frameio.event.type": event.type,
                "frameio.account.id": event.account_id,
                "frameio.resource.id": event.resource_id,
                "frameio.resource.type": event.resource.type,
                "frameio.user.id": event.user_id,
                "frameio.project.id": event.project_id,
                "frameio.workspace.id": event.workspace_id,
            },
        ) as span:
            if isinstance(event, ActionEvent):
                span.set_attribute("frameio.action.id", event.action_id)
                span.set_attribute("frameio.interaction.id", event.interaction_id)

            try:
                response = await next(event)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(self._status_error, str(exc))
                raise

            span.set_status(self._status_ok)
            return response
