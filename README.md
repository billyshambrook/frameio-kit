# frameio-kit: Build Powerful Frame.io Integrations in Minutes

**frameio-kit** is the fastest way to build robust, scalable integrations with Frame.io. Stop wrestling with webhook signatures, API authentication, and event parsing – focus on what makes your integration unique.

```python
import os
from frameio_kit import App, WebhookEvent, ActionEvent, Message

app = App()

# Single webhook - uses WEBHOOK_SECRET env var
@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

# Single action - uses CUSTOM_ACTION_SECRET env var
@app.on_action("my_app.analyze", "Analyze File", "Analyze this file")
async def analyze_file(event: ActionEvent):
    return Message(title="Analysis Complete", description="File analyzed successfully!")

# Multiple handlers with different secrets - pass explicit env vars
@app.on_webhook("comment.created", secret=os.environ["WEBHOOK_COMMENTS"])
async def on_comment(event: WebhookEvent):
    print(f"New comment on {event.resource_id}")
```

## 🚀 Quick Start

Ready to build your first Frame.io integration? Check out our comprehensive documentation:

- **[📖 Getting Started Guide](https://billyshambrook.github.io/frameio-kit/usage/getting_started/)** - Get up and running in 5 minutes
- **[🎣 Webhooks](https://billyshambrook.github.io/frameio-kit/usage/webhooks/)** - React to Frame.io events automatically  
- **[🎬 Custom Actions](https://billyshambrook.github.io/frameio-kit/usage/custom_actions/)** - Build interactive user experiences
- **[🌐 Client API](https://billyshambrook.github.io/frameio-kit/usage/client_api/)** - Make calls back to Frame.io's API
- **[🔄 Middleware](https://billyshambrook.github.io/frameio-kit/usage/middleware/)** - Add cross-cutting concerns to your integration

## ✨ Why frameio-kit?

- **Async-first architecture** - Handle thousands of concurrent webhooks without breaking a sweat
- **Decorator-based routing** - `@app.on_webhook` and `@app.on_action` make event handling trivial
- **Automatic validation** - Pydantic models give you full type safety and editor support
- **Secure by default** - Built-in signature verification for all requests
- **Zero boilerplate** - No manual JSON parsing or signature verification

## 📦 Installation

We recommend using [uv](https://docs.astral.sh/uv/) for fast, reliable installs:

```bash
uv add frameio-kit
```

Or with pip:
```bash
pip install frameio-kit
```

## 🔐 Environment Variables

frameio-kit uses environment variables for secrets, keeping your code clean and secure:

### Single Action/Webhook (Recommended)
Use the default environment variables when you have **one webhook and one action**:

```bash
# .env file
WEBHOOK_SECRET=your-webhook-secret-here
CUSTOM_ACTION_SECRET=your-action-secret-here
```

```python
# No secret parameter needed
@app.on_webhook("file.ready")
@app.on_action("my_app.process", "Process", "Process file")
```

### Multiple Actions/Webhooks (Different Secrets)
When you have **multiple handlers with different secrets**, pass each secret explicitly:

```bash
# .env file
WEBHOOK_FILES=secret-for-file-events
WEBHOOK_COMMENTS=secret-for-comment-events
CUSTOM_ACTION_ANALYZE=secret-for-analyze-action
CUSTOM_ACTION_PUBLISH=secret-for-publish-action
```

```python
import os

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_FILES"])
@app.on_webhook("comment.created", secret=os.environ["WEBHOOK_COMMENTS"])
@app.on_action("my_app.analyze", "Analyze", "Analyze file", secret=os.environ["CUSTOM_ACTION_ANALYZE"])
@app.on_action("my_app.publish", "Publish", "Publish file", secret=os.environ["CUSTOM_ACTION_PUBLISH"])
```

## 📚 Documentation

Complete documentation is available at [billyshambrook.github.io/frameio-kit](https://billyshambrook.github.io/frameio-kit/), including:

## 🤝 Contributing

Contributions are the heart of open source! We welcome improvements, bug fixes, and new features. Whether you're fixing a typo or adding a major feature, every contribution makes frameio-kit better.

### 📋 Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

### 🚀 Quick Start

1. **Fork and clone** the repository:
   ```bash
   git clone https://github.com/billyshambrook/frameio-kit.git
   cd frameio-kit
   ```

2. **Set up the development environment**:
   ```bash
   uv sync
   source .venv/bin/activate  # or activate via your IDE
   ```

3. **Install pre-commit hooks**:
   ```bash
   uv run pre-commit install
   ```

### 🧪 Development Workflow

**Run tests:**
```bash
uv run pytest
```

**Run code quality checks:**
```bash
uv run pre-commit run --all-files
```

**Build documentation:**
```bash
uv run mkdocs serve
```

### 🔄 Pull Request Process

1. **Fork** the repository on GitHub
2. **Create** a feature branch from `main`
3. **Make** your changes with tests and documentation
4. **Ensure** all tests and pre-commit hooks pass
5. **Commit** your changes with a clear message
6. **Push** to your fork and open a pull request

### 💡 Getting Help

- **Questions?** Open a [discussion](https://github.com/billyshambrook/frameio-kit/discussions)
- **Bug reports?** Open an [issue](https://github.com/billyshambrook/frameio-kit/issues)
- **Feature requests?** Start with a discussion first!
