# frameio-kit

A Python framework for building Frame.io integrations. Handle webhooks, custom actions, OAuth, and API calls with minimal boilerplate — you write the business logic, frameio-kit handles the rest.

```python
from frameio_kit import App, WebhookEvent, ActionEvent, Message

app = App()

@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

@app.on_action("my_app.analyze", name="Analyze File", description="Analyze this file")
async def analyze_file(event: ActionEvent):
    return Message(title="Analysis Complete", description="File analyzed successfully!")
```

## Installation

```bash
pip install frameio-kit
```

Optional extras for additional features:

```bash
pip install frameio-kit[otel]       # OpenTelemetry tracing
pip install frameio-kit[dynamodb]   # DynamoDB storage backend
pip install frameio-kit[install]    # Self-service installation UI
```

## Features

- **Decorator-based routing** — `@app.on_webhook` and `@app.on_action` map events to handler functions
- **Automatic validation** — Pydantic models give you full type safety and editor support
- **Secure by default** — built-in HMAC signature verification for all incoming requests
- **Middleware system** — add cross-cutting concerns like logging, auth, and tracing
- **OpenTelemetry integration** — optional distributed tracing with zero mandatory dependencies
- **OAuth integration** — Adobe Login support for user-specific authentication
- **Self-service installation** — branded install pages for workspace admins
- **ASGI-compatible** — mount into FastAPI, Starlette, or any ASGI framework
- **Built for Python 3.14+** with full type hints

## Documentation

Full documentation is available at [frameio-kit.dev](https://frameio-kit.dev):

- [Quickstart](https://frameio-kit.dev/getting-started/quickstart/) — build your first integration
- [Webhooks](https://frameio-kit.dev/guides/webhooks/) — react to Frame.io events
- [Custom Actions](https://frameio-kit.dev/guides/custom-actions/) — build interactive experiences
- [Client API](https://frameio-kit.dev/guides/client-api/) — make calls back to Frame.io
- [Middleware](https://frameio-kit.dev/guides/middleware/) — add cross-cutting concerns
- [OpenTelemetry](https://frameio-kit.dev/guides/opentelemetry/) — distributed tracing
- [User Authentication](https://frameio-kit.dev/guides/user-auth/) — OAuth flows
- [Self-Service Installation](https://frameio-kit.dev/guides/self-service-install/) — multi-tenant install UI
- [API Reference](https://frameio-kit.dev/reference/api/) — complete type documentation

## Contributing

Contributions are welcome! Whether you're fixing a typo or adding a feature, every contribution helps.

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
git clone https://github.com/billyshambrook/frameio-kit.git
cd frameio-kit
uv sync
uv run prek install
```

### Development

```bash
uv run pytest                # Run tests
uv run prek run --all-files  # Run static checks
uv run zensical serve        # Build docs locally
```

### Getting Help

- **Questions?** Open a [discussion](https://github.com/billyshambrook/frameio-kit/discussions)
- **Bug reports?** Open an [issue](https://github.com/billyshambrook/frameio-kit/issues)

## License

[MIT](LICENSE)
