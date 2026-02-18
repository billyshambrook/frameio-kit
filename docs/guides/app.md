# App Configuration

The [`App`](../reference/api.md#frameio_kit.App) class is the central entry point for your Frame.io integration. This guide covers app-level configuration options.

## Basic Initialization

```python
from frameio_kit import App

app = App()
```

!!! tip "Embedding in FastAPI"
    If you have an existing FastAPI application, use `app.include_router(kit.create_router())` to embed your frameio-kit routes. See [Embedding in FastAPI](mounting.md) for details.

## Configuration Options

### API Token

Provide an API token to enable authenticated calls to the Frame.io API via [`app.client`](../reference/api.md#frameio_kit.App.client):

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

See [Client API](client-api.md) for more details.

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

See [User Authentication](user-auth.md) for complete OAuth setup.

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

See [User Authentication - Storage Backends](user-auth.md#storage-backends) for details.

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

See [Self-Service Installation - Branding](self-service-install.md#branding) for details.

### Install Fields

Collect configuration from workspace admins during installation:

```python
from frameio_kit import App, OAuthConfig, InstallField, get_install_config

app = App(
    oauth=OAuthConfig(...),
    install=True,
    name="My Integration",
    install_fields=[
        InstallField(name="api_key", label="API Key", type="password", required=True),
        InstallField(name="environment", label="Environment", type="select",
                     options=("production", "staging"), default="production"),
    ],
)

@app.on_webhook("file.ready")
async def on_file_ready(event):
    config = get_install_config()
    api_key = config["api_key"]
```

See [Self-Service Installation - Custom Install Fields](self-service-install.md#custom-install-fields) for details.

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

## Environment Variables

frameio-kit uses the following environment variables. All are optional — each has an alternative configuration method.

| Variable | Purpose | Alternative |
|----------|---------|-------------|
| `WEBHOOK_SECRET` | Default signing secret for webhooks | Pass `secret=` to `@app.on_webhook` |
| `CUSTOM_ACTION_SECRET` | Default signing secret for custom actions | Pass `secret=` to `@app.on_action` |
| `FRAMEIO_TOKEN` | Frame.io API token for `app.client` | Pass `token=` to `App()` |
| `FRAMEIO_AUTH_ENCRYPTION_KEY` | Fernet key for encrypting stored tokens | Pass `encryption_key=` to `App()` |
| `ADOBE_CLIENT_ID` | Adobe OAuth client ID | Pass via `OAuthConfig(client_id=)` |
| `ADOBE_CLIENT_SECRET` | Adobe OAuth client secret | Pass via `OAuthConfig(client_secret=)` |

## See Also

- [Embedding in FastAPI](mounting.md) - Embed your App in an existing FastAPI application with `include_router()`
- [Webhooks](webhooks.md#dynamic-secret-resolution) - Webhook-specific secret resolution
- [Custom Actions](custom-actions.md#dynamic-secret-resolution) - Action-specific secret resolution
