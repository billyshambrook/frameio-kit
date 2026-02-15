# frameio-kit

A Python framework for building Frame.io integrations. Handle webhooks, custom actions, OAuth, and API calls with minimal boilerplate — you write the business logic, frameio-kit handles the rest.

```python
from frameio_kit import App, WebhookEvent, ActionEvent, Message

app = App()

@app.on_webhook("file.ready", secret="your-secret")
async def on_file_ready(event: WebhookEvent):
    print(f"File is ready!")

@app.on_action("my_app.analyze", name="Analyze File", description="Analyze this file", secret="your-secret")
async def analyze_file(event: ActionEvent):
    return Message(title="Analysis Complete", description="File analyzed successfully!")
```

## Where to Start

**New to Frame.io app development?** Read [How Frame.io Apps Work](concepts.md) for an overview of webhooks, custom actions, and authentication.

**Ready to build?** The [Quickstart](getting-started/quickstart.md) gets you from zero to a working integration in minutes.

**Know what you need?** Jump directly to the [Guides](guides/app.md) for in-depth coverage of specific features.

## Key Features

- **Decorator-based routing** — `@app.on_webhook` and `@app.on_action` map events to handler functions
- **Automatic validation** — Pydantic models give you full type safety and editor support
- **Secure by default** — built-in signature verification for all incoming requests
- **OAuth integration** — Adobe Login support for user-specific authentication
- **Self-service installation** — branded install pages for workspace admins
- **ASGI-compatible** — mount into FastAPI, Starlette, or any ASGI framework
- **Built for Python 3.14+** with full type hints

## Learn More

- [How Frame.io Apps Work](concepts.md) — understand the concepts before diving in
- [Installation](getting-started/installation.md) — install frameio-kit and set up prerequisites
- [Quickstart](getting-started/quickstart.md) — build your first integration
- [Guides](guides/app.md) — in-depth guides for every feature
- [API Reference](reference/api.md) — complete documentation for all classes and methods
- [Frame.io Developer Portal](https://next.developer.frame.io) — official Frame.io v4 API documentation
