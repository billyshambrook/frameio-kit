# Middleware

Middleware provides a powerful way to add cross-cutting concerns to your Frame.io integration without cluttering your handler functions. You can use middleware for logging, authentication, metrics collection, error handling, and more.

## Why Use Middleware?

Middleware is particularly useful when you need to:

- **Add logging or monitoring** to all requests
- **Implement authentication or authorization** checks
- **Collect metrics** about request processing times
- **Handle errors** consistently across all handlers
- **Add request/response transformation** logic
- **Implement rate limiting** or other security measures

Instead of duplicating this logic in every handler, middleware allows you to write it once and apply it globally.

## How Middleware Works

Middleware in `frameio-kit` follows a chain-of-responsibility pattern. When an event is received, it flows through each middleware in the order they were registered, then to your handler, and finally back through the middleware in reverse order.

```
Request → Middleware 1 → Middleware 2 → Handler → Middleware 2 → Middleware 1 → Response
```

## Middleware Hooks

The [`Middleware`](../api_reference.md#frameio_kit.Middleware) base class provides three hooks you can override:

### [`__call__(event, next)`](../api_reference.md#frameio_kit.Middleware.__call__)

The main entry point that runs for **every event** (both webhooks and actions). This is where you implement logic that should apply universally.

```python
async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
    # Code here runs before every event
    result = await next(event)  # Call the next middleware or handler
    # Code here runs after every event
    return result
```

### [`on_webhook(event, next)`](../api_reference.md#frameio_kit.Middleware.on_webhook)

Runs only for **webhook events**. This is called automatically by the base [`__call__`](../api_reference.md#frameio_kit.Middleware.__call__) method when the event is a [`WebhookEvent`](../api_reference.md#frameio_kit.WebhookEvent).

```python
async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
    # Code here runs only for webhook events
    result = await next(event)
    return result
```

### [`on_action(event, next)`](../api_reference.md#frameio_kit.Middleware.on_action)

Runs only for **custom action events**. This is called automatically by the base [`__call__`](../api_reference.md#frameio_kit.Middleware.__call__) method when the event is an [`ActionEvent`](../api_reference.md#frameio_kit.ActionEvent).

```python
async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
    # Code here runs only for action events
    result = await next(event)
    return result
```

## Important: Overriding [`__call__`](../api_reference.md#frameio_kit.Middleware.__call__)

When you override [`__call__`](../api_reference.md#frameio_kit.Middleware.__call__), you completely replace the base implementation. This means:

- **Without `super()`**: The [`on_webhook`](../api_reference.md#frameio_kit.Middleware.on_webhook) and [`on_action`](../api_reference.md#frameio_kit.Middleware.on_action) methods on the same middleware class will **not** be called
- **With `super()`**: The original dispatch logic is preserved, so [`on_webhook`](../api_reference.md#frameio_kit.Middleware.on_webhook) and [`on_action`](../api_reference.md#frameio_kit.Middleware.on_action) will still be called

## Setting Up Middleware

To use middleware, pass a list of middleware instances when creating your [`App`](../api_reference.md#frameio_kit.App):

```python
from frameio_kit import App, Middleware

app = App(
    token=os.getenv("FRAMEIO_TOKEN"),
    middleware=[
        LoggingMiddleware(),
        TimingMiddleware(),
        # Add more middleware here
    ]
)
```

## Example 1: Using [`__call__`](../api_reference.md#frameio_kit.Middleware.__call__) for Universal Logic

```python
import time
from frameio_kit import App, Middleware, WebhookEvent, Message
from frameio_kit.middleware import AnyEvent, NextFunc, AnyResponse

class TimingMiddleware(Middleware):
    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        start_time = time.monotonic()

        try:
            return await next(event)
        finally:
            duration = time.monotonic() - start_time
            print(f"Completed in {duration:.2f}s")

# Usage
app = App(
    token=os.getenv("FRAMEIO_TOKEN"),
    middleware=[TimingMiddleware()]
)

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print("File ready")
```

## Example 2: Using Specific Hooks

```python
from frameio_kit import App, Middleware, WebhookEvent, ActionEvent, Message
from frameio_kit.middleware import NextFunc, AnyResponse

class LoggingMiddleware(Middleware):
    async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
        print(f"Webhook: {event.type} for {event.resource_id}")
        return await next(event)
    
    async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
        print(f"Action: {event.type} by {event.user.name}")
        return await next(event)

class ValidationMiddleware(Middleware):
    async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
        if not event.resource_id:
            raise ValueError("Missing resource_id")
        return await next(event)

# Usage
app = App(
    token=os.getenv("FRAMEIO_TOKEN"),
    middleware=[LoggingMiddleware(), ValidationMiddleware()]
)

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print("File ready")

@app.on_action("my_app.analyze", "Analyze", "Analyze file", os.environ["ACTION_SECRET"])
async def analyze_file(event: ActionEvent):
    return Message(title="Analysis Complete", description="Done!")
```

## Best Practices

1. **Order matters**: Middleware runs in the order you register it. Put error handling middleware first.

2. **Keep middleware focused**: Each middleware should have a single responsibility.

3. **Use `super().__call__()` when needed**: If you override [`__call__`](../api_reference.md#frameio_kit.Middleware.__call__) but still want the automatic dispatch to [`on_webhook`](../api_reference.md#frameio_kit.Middleware.on_webhook)/[`on_action`](../api_reference.md#frameio_kit.Middleware.on_action), use `super().__call__(event, next)`.

4. **Handle exceptions gracefully**: Consider whether to re-raise exceptions or return default responses and when to use `try`/`finally` to ensure cleanup.

5. **Make middleware configurable**: Use `__init__` to accept configuration parameters.

6. **Test your middleware**: Write unit tests to ensure your middleware behaves correctly in isolation.

## Advanced Patterns

### Conditional Middleware

You can create middleware that only runs under certain conditions:

```python
class ConditionalMiddleware(Middleware):
    def __init__(self, condition_func):
        self.condition_func = condition_func
    
    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        if self.condition_func(event):
            # Only run middleware logic if condition is met
            print(f"Condition met for {event.type}")
        return await next(event)

# Usage
app = App(
    middleware=[
        ConditionalMiddleware(lambda e: e.type.startswith("file.")),
    ]
)
```

### Middleware with State

Middleware can maintain state across requests:

```python
class RateLimitMiddleware(Middleware):
    def __init__(self, max_requests_per_minute=60):
        self.max_requests = max_requests_per_minute
        self.requests = {}  # Track requests by resource_id
    
    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        current_time = time.time()
        resource_id = event.resource_id
        
        # Clean old entries
        self.requests[resource_id] = [
            req_time for req_time in self.requests.get(resource_id, [])
            if current_time - req_time < 60
        ]
        
        # Check rate limit
        if len(self.requests.get(resource_id, [])) >= self.max_requests:
            raise Exception(f"Rate limit exceeded for resource {resource_id}")
        
        # Record this request
        self.requests.setdefault(resource_id, []).append(current_time)
        
        return await next(event)
```

This comprehensive middleware system gives you the flexibility to add powerful cross-cutting concerns to your Frame.io integrations while keeping your handler code clean and focused.
