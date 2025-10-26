# Middleware

Middleware adds cross-cutting concerns like logging, metrics, and error handling to your Frame.io integration without cluttering handler functions.

## When to Use Middleware

Use middleware when you need to:

- Add logging or monitoring to all requests
- Collect metrics about processing times
- Handle errors consistently
- Implement authentication checks
- Add rate limiting or security measures

## How It Works

Middleware follows a chain pattern. Events flow through each middleware in order, then to your handler, and back through middleware in reverse:

```
Request → Middleware 1 → Middleware 2 → Handler → Middleware 2 → Middleware 1 → Response
```

## Setup

Pass middleware instances when creating your app:

```python
from frameio_kit import App, Middleware

app = App(
    token=os.getenv("FRAMEIO_TOKEN"),
    middleware=[
        LoggingMiddleware(),
        TimingMiddleware(),
    ]
)
```

## Middleware Hooks

The `Middleware` base class provides three hooks:

### `__call__` - Universal Hook

Runs for **all events** (webhooks and actions):

```python
from frameio_kit import Middleware
from frameio_kit.middleware import AnyEvent, NextFunc, AnyResponse

class TimingMiddleware(Middleware):
    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        start_time = time.monotonic()
        try:
            return await next(event)
        finally:
            duration = time.monotonic() - start_time
            print(f"Completed in {duration:.2f}s")
```

### `on_webhook` - Webhook-Specific

Runs only for **webhook events**:

```python
async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
    print(f"Webhook: {event.type}")
    return await next(event)
```

### `on_action` - Action-Specific

Runs only for **custom action events**:

```python
async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
    print(f"Action: {event.type} by {event.user.name}")
    return await next(event)
```

## Examples

### Logging Middleware

```python
from frameio_kit import Middleware, WebhookEvent, ActionEvent
from frameio_kit.middleware import NextFunc, AnyResponse

class LoggingMiddleware(Middleware):
    async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
        print(f"Webhook: {event.type} for {event.resource_id}")
        return await next(event)

    async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
        print(f"Action: {event.type} by {event.user.name}")
        return await next(event)
```

### Error Handling Middleware

```python
class ErrorHandlerMiddleware(Middleware):
    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        try:
            return await next(event)
        except Exception as e:
            print(f"Error processing {event.type}: {e}")
            raise
```

### Conditional Middleware

```python
class ConditionalMiddleware(Middleware):
    def __init__(self, condition_func):
        self.condition_func = condition_func

    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        if self.condition_func(event):
            print(f"Condition met for {event.type}")
        return await next(event)

# Usage
app = App(
    middleware=[
        ConditionalMiddleware(lambda e: e.type.startswith("file.")),
    ]
)
```

## Important Notes

**Order matters**: Middleware runs in the order you register it

**Overriding `__call__`**: When you override `__call__`, you replace the base implementation. To preserve automatic dispatch to `on_webhook` and `on_action`, call `super().__call__(event, next)`

**Always call `next`**: Your middleware must call `await next(event)` to continue the chain

**Error handling**: Use `try`/`finally` for cleanup code that must run even if errors occur

## Best Practices

**Keep middleware focused** - Each middleware should have a single responsibility

**Order error handlers first** - Put error handling middleware at the start of the chain

**Make middleware configurable** - Use `__init__` to accept configuration parameters

**Test in isolation** - Write unit tests for middleware independently
