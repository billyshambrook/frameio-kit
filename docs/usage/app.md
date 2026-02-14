# App Configuration

The [`App`](../api_reference.md#frameio_kit.App) class is the central entry point for your Frame.io integration. This guide covers app-level configuration options.

## Basic Initialization

```python
from frameio_kit import App

app = App()
```

!!! tip "Mounting to Existing Applications"
    If you have an existing ASGI application (FastAPI, Starlette, etc.), you can mount your frameio-kit `App` directly to it without any code changes. See [Mounting to Existing Apps](mounting.md) for details.

## Configuration Options

### API Token

Provide an API token to enable authenticated calls to the Frame.io API via [`app.client`](../api_reference.md#frameio_kit.App.client):

```python
import os

app = App(token=os.getenv("FRAMEIO_TOKEN"))

# Use the client in handlers
@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    file = await app.client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )
    print(f"File name: {file.data.name}")
```

See [Client API](client_api.md) for more details.

### Middleware

Add middleware for logging, metrics, error handling, and more:

```python
from frameio_kit import App, Middleware

class LoggingMiddleware(Middleware):
    async def __call__(self, event, next):
        print(f"Processing event: {event.type}")
        response = await next(event)
        print(f"Event processed: {event.type}")
        return response

app = App(middleware=[LoggingMiddleware()])
```

See [Middleware](middleware.md) for detailed examples.

### OAuth Configuration

Enable Adobe Login OAuth for user authentication:

```python
from frameio_kit import App, OAuthConfig

app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("OAUTH_CLIENT_ID"),
        client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
        redirect_url="https://your-app.com/auth/callback",
    ),
    encryption_key=os.getenv("ENCRYPTION_KEY"),
)
```

See [User Authentication](user_auth.md) for complete OAuth setup.

### Storage and Encryption

Storage and encryption are configured at the `App` level and shared between OAuth token management and the installation system:

```python
from frameio_kit import App, OAuthConfig, DynamoDBStorage

app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("OAUTH_CLIENT_ID"),
        client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    ),
    storage=DynamoDBStorage(table_name="frameio-app-data"),
    encryption_key=os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"),
)
```

See [User Authentication - Storage Backends](user_auth.md#storage-backends) for details.

### Branding

Customize the install and auth callback pages with your brand identity:

```python
app = App(
    oauth=OAuthConfig(...),
    install=True,
    name="My Video Tool",
    description="AI-powered video analysis for your team.",
    logo_url="https://myapp.com/logo.png",
    primary_color="#1a73e8",
    accent_color="#34a853",
    show_powered_by=False,
)
```

See [Installation System - Branding](installation.md#branding) for details.

## Secret Resolution Precedence

The framework follows this precedence order (highest to lowest):

1. **Explicit string secret** at decorator (`secret="..."`)
2. **Decorator-level resolver** function (`secret=my_resolver`)
3. **Install system resolver** (when `install=True`, secrets are auto-managed)
4. **Environment variables** (`WEBHOOK_SECRET` / `CUSTOM_ACTION_SECRET`)

This allows you to:

- Use the install system for automatic secret management
- Override with decorator-level resolver for specific handlers
- Override with static secrets for testing or special cases

## Best Practices

1. **Keep secrets secure** - Never log or expose secrets in error messages
2. **Cache when possible** - If secrets don't change often, consider caching
3. **Handle errors gracefully** - Provide clear error messages when secret lookup fails
4. **Test secret resolution** - Ensure resolvers work correctly before deploying
5. **Monitor resolver performance** - Secret lookup happens on every request

## See Also

- [Mounting to Existing Apps](mounting.md) - Mount your App to FastAPI, Starlette, or any ASGI framework
- [Webhooks](webhooks.md#dynamic-secret-resolution) - Webhook-specific secret resolution
- [Custom Actions](custom_actions.md#dynamic-secret-resolution) - Action-specific secret resolution
