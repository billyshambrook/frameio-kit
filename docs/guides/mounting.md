# Mounting to Existing Applications

You can mount your frameio-kit [`App`](../reference/api.md#frameio_kit.App) into any existing ASGI-compatible application without changing your existing code. Since `App` is fully ASGI-compliant, it integrates seamlessly with frameworks like **FastAPI**, **Starlette**, **Quart**, and any other ASGI server.

!!! tip "ASGI Compatibility"
    The examples below use FastAPI, but the same mounting approach works with any ASGI-compatible framework. Simply use your framework's mount or route mounting mechanism.

## Why Mount to an Existing Application?

Mounting to an existing application is useful when you want to:

- **Consolidate services** -- Run your Frame.io integration alongside existing HTTP APIs.
- **Share infrastructure** -- Reuse middleware, logging, and monitoring from your existing app.
- **Unified deployment** -- Deploy one application instead of multiple services.
- **Common endpoints** -- Provide health checks, metrics, and other shared endpoints.

## Exposed Routes

Before mounting, understand what routes your frameio-kit `App` exposes. The paths below are **relative to the mount point** (for example, `/frameio` if you mount at that prefix):

### Always Available

- **`POST /`** - Main webhook and custom action endpoint

### OAuth Routes (when configured)

- **`GET /auth/login`** - Initiates Adobe Login OAuth flow
- **`GET /auth/callback`** - Handles OAuth callback

!!! note "OAuth Routes"
    OAuth routes are only available when you configure the `App` with an [`OAuthConfig`](../reference/api.md#frameio_kit.OAuthConfig). See [User Authentication](user-auth.md) for details.

## Mounting Options

### Option 1: Mount at a Path Prefix (Recommended)

Mount your frameio-kit `App` at a specific path prefix to keep routes organized:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from frameio_kit import App, WebhookEvent, ActionEvent, Message

# Your frameio-kit app
frameio_app = App()

@frameio_app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

@frameio_app.on_action("my_app.process", name="Process", description="Process this file")
async def process_file(event: ActionEvent):
    return Message(title="Processing", description="File is being processed")

# Lifespan to clean up frameio-kit resources on shutdown
@asynccontextmanager
async def lifespan(app):
    yield
    await frameio_app.close()

# Your existing FastAPI app
fastapi_app = FastAPI(lifespan=lifespan)

# Mount at /frameio prefix
fastapi_app.mount("/frameio", frameio_app)

# Your existing FastAPI routes work normally
@fastapi_app.get("/")
async def root():
    return {"message": "Hello World"}

@fastapi_app.get("/health")
async def health():
    return {"status": "healthy"}
```

**With this setup:**

- Frame.io webhooks/actions → `https://your-domain.com/frameio/`
- OAuth login (if enabled) → `https://your-domain.com/frameio/auth/login`
- OAuth callback (if enabled) → `https://your-domain.com/frameio/auth/callback`
- Your routes remain at their original paths

### Option 2: Mount at Root Path

If you want Frame.io events at the root path, mount at `/`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from frameio_kit import App, WebhookEvent

frameio_app = App()

@frameio_app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

@asynccontextmanager
async def lifespan(app):
    yield
    await frameio_app.close()

fastapi_app = FastAPI(lifespan=lifespan)

# Define your FastAPI routes BEFORE mounting
@fastapi_app.get("/health")
async def health():
    return {"status": "healthy"}

@fastapi_app.get("/metrics")
async def metrics():
    return {"requests": 1000}

# Mount at root - handles all POST requests to "/"
fastapi_app.mount("/", frameio_app)
```

!!! warning "Route Order Matters"
    When mounting at `/`, frameworks like FastAPI resolve routes in registration order. Define your application routes **before** mounting frameio-kit; otherwise, the mounted `App` may intercept requests that you expect to hit your own routes.

**With this setup:**

- Frame.io webhooks/actions → `https://your-domain.com/`
- OAuth login (if enabled) → `https://your-domain.com/auth/login`
- OAuth callback (if enabled) → `https://your-domain.com/auth/callback`
- Your routes remain accessible at their defined paths


!!! tip "frameio-kit Middleware"
    For Frame.io-specific middleware (that should only run on webhook/action handlers), use frameio-kit's built-in [Middleware](middleware.md) system instead of application-level middleware.

## Lifespan

When mounting a frameio-kit `App` as a sub-application, the inner app's `lifespan` parameter **will not run** — ASGI frameworks only invoke the outermost application's lifespan. Manage shared resources in the parent app's lifespan and call `frameio_app.close()` from there:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from frameio_kit import App
import httpx

frameio_app = App()

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient() as http_client:
        # Store on the frameio app or pass through your own mechanism
        app.state.http_client = http_client
        yield
    await frameio_app.close()

fastapi_app = FastAPI(lifespan=lifespan)
fastapi_app.mount("/frameio", frameio_app)
```

## Running Your Application

Use `uvicorn` (or any ASGI server) to run your combined application:

```bash
# Point to your application instance
uvicorn main:fastapi_app --host 0.0.0.0 --port 8000 --reload
```

## Deployment Considerations

### Health Checks

Add a health check endpoint to monitor both your application and frameio-kit:

```python
@fastapi_app.get("/health")
async def health():
    return {"status": "healthy"}
```

## Troubleshooting

### Routes Not Found

If Frame.io events return 404:

1. Verify the mount path matches your webhook/action URLs in Frame.io
2. Check that you're using the correct HTTP method (`POST` for webhooks/actions)
3. Ensure the mount path doesn't conflict with existing application routes or other mounted apps.

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
