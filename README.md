# frameio-kit

Build powerful Frame.io integrations with minimal boilerplate. Stop wrestling with webhook signatures and API authentication – focus on what makes your integration unique.

```python
from frameio_kit import App, WebhookEvent, ActionEvent, Message

app = App()

@app.on_webhook("file.ready", secret="your-webhook-secret")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

@app.on_action("my_app.analyze", "Analyze", "Analyze file", "your-action-secret")
async def analyze_file(event: ActionEvent):
    return Message(title="Done!", description="File analyzed successfully")
```

## Features

- **Decorator-based routing** - Simple `@app.on_webhook` and `@app.on_action` decorators
- **Type-safe** - Full Pydantic models and type hints throughout
- **Async-first** - Built on modern async Python for high performance
- **Secure** - Automatic signature verification for all incoming requests
- **Batteries included** - Forms, middleware, OAuth, and Frame.io API client

## Installation

```bash
uv add frameio-kit
# or
pip install frameio-kit
```

## Documentation

**[Read the full documentation →](https://billyshambrook.github.io/frameio-kit/)**

- [Getting Started](https://billyshambrook.github.io/frameio-kit/usage/getting_started/) - Build your first integration in 5 minutes
- [Webhooks](https://billyshambrook.github.io/frameio-kit/usage/webhooks/) - React to Frame.io events
- [Custom Actions](https://billyshambrook.github.io/frameio-kit/usage/custom_actions/) - Build interactive workflows
- [Client API](https://billyshambrook.github.io/frameio-kit/usage/client_api/) - Make calls to Frame.io's API
- [API Reference](https://billyshambrook.github.io/frameio-kit/api_reference/) - Complete API documentation

## Contributing

Contributions welcome! See the [contribution guidelines](CONTRIBUTING.md) for details on:

- Setting up your development environment
- Running tests and code quality checks
- Submitting pull requests

### Quick Setup

```bash
git clone https://github.com/billyshambrook/frameio-kit.git
cd frameio-kit
uv sync
uv run pre-commit install
uv run pytest
```

## License

MIT License - see [LICENSE](LICENSE) for details.
