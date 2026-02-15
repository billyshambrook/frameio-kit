# OpenTelemetry

`frameio-kit` includes an optional [`OpenTelemetryMiddleware`](../reference/api.md#frameio_kit.OpenTelemetryMiddleware) that provides distributed tracing for incoming webhook and custom action events. Each event is wrapped in a span with rich attributes describing the event context.

## Why Use OpenTelemetry?

OpenTelemetry tracing is useful when you need to:

- **Monitor request latency** and identify slow handlers
- **Debug production issues** by correlating Frame.io events with downstream service calls
- **Track event throughput** across your integration
- **Export traces** to your observability platform (Datadog, Jaeger, Grafana Tempo, etc.)

## Installation

The middleware requires the `opentelemetry-api` package, available via the `otel` extra:

```bash
pip install frameio-kit[otel]
```

You'll also need the OpenTelemetry SDK and an exporter for your platform:

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp
```

## Quick Start

Add [`OpenTelemetryMiddleware`](../reference/api.md#frameio_kit.OpenTelemetryMiddleware) to your app's middleware list:

```python
import os

from frameio_kit import App, OpenTelemetryMiddleware, WebhookEvent

app = App(
    token=os.getenv("FRAMEIO_TOKEN"),
    middleware=[OpenTelemetryMiddleware()],
)

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready")
```

That's it. Every event processed by your app now produces a trace span.

## How It Works

The middleware creates a span for each incoming event using the [`__call__`](../reference/api.md#frameio_kit.Middleware.__call__) hook, wrapping the entire middleware chain and handler execution.

```
Request → OpenTelemetryMiddleware (span start) → Other Middleware → Handler → (span end) → Response
```

### Span Details

| Property | Value |
|----------|-------|
| **Name** | `frameio {event.type}` (e.g. `frameio file.ready`) |
| **Kind** | `SERVER` |

### Span Attributes

These attributes are set on every span:

| Attribute | Description | Example |
|-----------|-------------|---------|
| `frameio.event.type` | The event type | `file.ready` |
| `frameio.account.id` | Account ID | `acc_123` |
| `frameio.resource.id` | Resource ID | `file_456` |
| `frameio.resource.type` | Resource type | `file` |
| `frameio.user.id` | User ID | `user_789` |
| `frameio.project.id` | Project ID | `proj_012` |
| `frameio.workspace.id` | Workspace ID | `ws_345` |

For custom action events, two additional attributes are included:

| Attribute | Description | Example |
|-----------|-------------|---------|
| `frameio.action.id` | Action ID | `act_678` |
| `frameio.interaction.id` | Interaction ID | `int_901` |

### Error Recording

If a handler raises an exception, the middleware records the exception on the span and sets the span status to `ERROR` before re-raising. This ensures errors are visible in your tracing backend while preserving the app's normal error handling.

## Configuration

[`OpenTelemetryMiddleware`](../reference/api.md#frameio_kit.OpenTelemetryMiddleware) accepts two optional parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tracer_name` | `str` | `"frameio_kit"` | Name passed to `trace.get_tracer()`. Appears as the instrumentation scope in your tracing backend. |
| `tracer_provider` | `TracerProvider \| None` | `None` | An explicit tracer provider. When `None`, uses the globally configured provider. |

```python
from opentelemetry.sdk.trace import TracerProvider

provider = TracerProvider()
# ... configure your provider with processors and exporters ...

app = App(
    middleware=[
        OpenTelemetryMiddleware(
            tracer_name="my_integration",
            tracer_provider=provider,
        ),
    ],
)
```

## Example: Exporting Traces with OTLP

A complete example that exports traces to an OTLP-compatible backend (Jaeger, Grafana Tempo, Datadog Agent, etc.):

```python
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

from frameio_kit import App, OpenTelemetryMiddleware, WebhookEvent

# Configure the tracer provider
resource = Resource.create({"service.name": "my-frameio-integration"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())  # Defaults to localhost:4317
)
trace.set_tracer_provider(provider)

# Create the app with tracing
app = App(
    token=os.getenv("FRAMEIO_TOKEN"),
    middleware=[OpenTelemetryMiddleware()],
)

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready")
```

## Combining with Other Middleware

[`OpenTelemetryMiddleware`](../reference/api.md#frameio_kit.OpenTelemetryMiddleware) works alongside any other middleware. Place it **first** in the list so spans capture the full processing time including other middleware:

```python
app = App(
    middleware=[
        OpenTelemetryMiddleware(),  # First: captures total duration
        AuthMiddleware(),
        LoggingMiddleware(),
    ],
)
```

## No-Op Behavior

When no OpenTelemetry SDK is configured, the `opentelemetry-api` package provides a no-op tracer. This means the middleware is safe to leave enabled in all environments with near-zero overhead — no spans are created or exported unless you explicitly configure a tracer provider.

!!! tip
    This makes it easy to enable tracing only in production by configuring a `TracerProvider` there, while development environments silently skip tracing with no code changes.
