# Embedding in FastAPI

frameio-kit is built on FastAPI. The [`App`](../reference/api.md#frameio_kit.App) class provides a `create_router()` method that returns a standard FastAPI `APIRouter`, which you can embed into your existing FastAPI application using `include_router()`. This means routes appear in your OpenAPI docs and you can use FastAPI dependency injection alongside frameio-kit.

!!! tip "Standalone Usage"
    You don't need an existing FastAPI app. The `App` class is also a fully ASGI-compatible application that can be run directly with Uvicorn.

## Why Embed in an Existing Application?

Embedding is useful when you want to:

- **Consolidate services** -- Run your Frame.io integration alongside existing HTTP APIs.
- **Share infrastructure** -- Reuse middleware, logging, and monitoring from your existing app.
- **Unified deployment** -- Deploy one application instead of multiple services.
- **Common endpoints** -- Provide health checks, metrics, and other shared endpoints.

## Exposed Routes

Before embedding, understand what routes your frameio-kit `App` exposes. The paths below are **relative to the prefix** you choose when calling `include_router()`:

### Always Available

- **`POST /`** - Main webhook and custom action endpoint

### OAuth Routes (when configured)

- **`GET /auth/login`** - Initiates Adobe Login OAuth flow
- **`GET /auth/callback`** - Handles OAuth callback

!!! note "OAuth Routes"
    OAuth routes are only available when you configure the `App` with an [`OAuthConfig`](../reference/api.md#frameio_kit.OAuthConfig). See [User Authentication](user-auth.md) for details.

### Install Routes (when configured)

- **`GET /install`** - Self-service installation landing page
- **`GET /install/login`** - Initiates OAuth for install session
- **`GET /install/callback`** - Handles install OAuth callback
- **`GET /install/workspaces`** - HTMX: load workspace dropdown
- **`GET /install/status`** - HTMX: workspace installation status
- **`POST /install/execute`** - HTMX: perform install or update
- **`POST /install/uninstall`** - HTMX: perform uninstall
- **`POST /install/logout`** - Clear session and redirect

!!! note "Install Routes"
    Install routes are only available when you configure the `App` with `install=True`. See [Installation](installation.md) for details.

## Embedding Options

### Option 1: Embed at a Path Prefix (Recommended)

Use `include_router()` with a `prefix` to keep routes organized:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from frameio_kit import App, WebhookEvent, ActionEvent, Message

# Your frameio-kit app
kit = App()

@kit.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

@kit.on_action("my_app.process", name="Process", description="Process this file")
async def process_file(event: ActionEvent):
    return Message(title="Processing", description="File is being processed")

# Lifespan to clean up frameio-kit resources on shutdown
@asynccontextmanager
async def lifespan(app):
    yield
    await kit.close()

# Your existing FastAPI app
app = FastAPI(lifespan=lifespan)

# Embed at /frameio prefix
app.include_router(kit.create_router(), prefix="/frameio")

# Your existing FastAPI routes work normally
@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**With this setup:**

- Frame.io webhooks/actions → `https://your-domain.com/frameio/`
- OAuth login (if enabled) → `https://your-domain.com/frameio/auth/login`
- OAuth callback (if enabled) → `https://your-domain.com/frameio/auth/callback`
- Install page (if enabled) → `https://your-domain.com/frameio/install`
- Install callback (if enabled) → `https://your-domain.com/frameio/install/callback`
- Your routes remain at their original paths

### Option 2: Embed at Root Path

If you want Frame.io events at the root path, include without a prefix:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from frameio_kit import App, WebhookEvent

kit = App()

@kit.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

@asynccontextmanager
async def lifespan(app):
    yield
    await kit.close()

app = FastAPI(lifespan=lifespan)

# Define your FastAPI routes
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    return {"requests": 1000}

# Include at root
app.include_router(kit.create_router())
```

**With this setup:**

- Frame.io webhooks/actions → `https://your-domain.com/`
- OAuth login (if enabled) → `https://your-domain.com/auth/login`
- OAuth callback (if enabled) → `https://your-domain.com/auth/callback`
- Install page (if enabled) → `https://your-domain.com/install`
- Install callback (if enabled) → `https://your-domain.com/install/callback`
- Your routes remain accessible at their defined paths


!!! tip "frameio-kit Middleware"
    For Frame.io-specific middleware (that should only run on webhook/action handlers), use frameio-kit's built-in [Middleware](middleware.md) system instead of application-level middleware.

## Running Your Application

Use `uvicorn` (or any ASGI server) to run your combined application:

```bash
# Point to your application instance
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Deployment Considerations

### Health Checks

Add a health check endpoint to monitor both your application and frameio-kit:

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

## Troubleshooting

### Routes Not Found

If Frame.io events return 404:

1. Verify the prefix matches your webhook/action URLs in Frame.io
2. Check that you're using the correct HTTP method (`POST` for webhooks/actions)
3. Ensure the prefix doesn't conflict with existing application routes

### Signature Validation Fails

If you get "Invalid signature" errors:

1. Verify the secrets match the values configured in Frame.io for your webhook or custom action.
2. Ensure middleware isn't modifying the request body before frameio-kit validates it
3. Check that `X-Frameio-Request-Timestamp` header is being passed through

## Next Steps

- **[App Configuration](app.md)** - Configure middleware, OAuth, and dynamic secret resolution
- **[Webhooks](webhooks.md)** - Learn about webhook event types and best practices
- **[Custom Actions](custom-actions.md)** - Build interactive forms and workflows
- **[User Authentication](user-auth.md)** - Enable Adobe Login OAuth for user-specific actions
