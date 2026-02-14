# Webhooks

Webhooks are automated, non-interactive messages sent from Frame.io to your application when specific events occur. They're perfect for building reactive workflows that respond to changes in real-time without user intervention.

## Why Use Webhooks?

Webhooks are ideal when you need to:

- **React to file changes** (uploads, processing completion, etc.)
- **Monitor project activity** (comments, approvals, status changes)
- **Trigger automated workflows** (notifications, data processing, integrations)
- **Keep external systems in sync** with Frame.io events
- **Build event-driven applications** that respond to Frame.io activity

## How Webhooks Work

1. **Event occurs** in Frame.io (file uploaded, comment added, etc.)
2. **Frame.io sends HTTP POST** to your configured webhook URL
3. **Your handler processes** the event data

```
Frame.io Event → HTTP POST → Your Handler
```

## Webhook Decorator

Use the [`@app.on_webhook`](../api_reference.md#frameio_kit.App.on_webhook) decorator to register handlers:

```python
import os

# Single webhook - use default WEBHOOK_SECRET env var
@app.on_webhook(event_type="file.ready")
async def on_file_ready(event: WebhookEvent):
    # Handle the event
    pass

# Multiple webhooks with different secrets - use explicit env vars
@app.on_webhook(event_type="file.ready", secret=os.environ["FILE_READY_WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    pass

@app.on_webhook(event_type="comment.created", secret=os.environ["COMMENTS_WEBHOOK_SECRET"])
async def on_comment_created(event: WebhookEvent):
    pass
```

### Parameters

- [`event_type`](../api_reference.md#frameio_kit.App.on_webhook\(event_type\)) *(str | list[str])*: The event name(s) to listen for
- [`secret`](../api_reference.md#frameio_kit.App.on_webhook\(secret\)) *(str | None, optional)*: The signing secret from Frame.io. If not provided, falls back to the `WEBHOOK_SECRET` environment variable. Explicit parameter takes precedence over environment variable.

!!! note "Environment Variables"
    **Single webhook:** Use the default `WEBHOOK_SECRET` environment variable and omit the `secret` parameter.

    **Multiple webhooks with different secrets:** Pass each secret explicitly via `secret=os.environ["WEBHOOK_NAME_WEBHOOK_SECRET"]` to keep secrets out of your code while supporting multiple webhook configurations.

## Webhook Event Object

The [`WebhookEvent`](../api_reference.md#frameio_kit.WebhookEvent) object provides typed access to all event data:

```python
from frameio_kit import WebhookEvent

async def handler(event: WebhookEvent):
    print(event.type)           # "file.ready"
    print(event.resource_id)    # "abc123"
    print(event.account_id)     # "acc_456"
    print(event.user_id)        # "user_789"
    print(event.project_id)     # "proj_101"
    print(event.workspace_id)   # "ws_123"
```

## Event Types

See [Webhook Event Subscriptions](https://developer.staging.frame.io/platform/docs/guides/webhooks#webhook-event-subscriptions) for the full list of event types.

## Example 1: Single Webhook (Default Env Var)

```python
from frameio_kit import App, WebhookEvent, Message

app = App()

# Single webhook - WEBHOOK_SECRET env var used automatically
@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready for processing")

    # Simulate some processing
    await process_file(event.resource_id)

async def process_file(file_id: str):
    # Your processing logic here
    pass
```

## Example 2: Multiple Webhooks (Explicit Env Vars)

```python
import os
from frameio_kit import App, WebhookEvent

app = App()

# Multiple webhooks with different secrets - use explicit env vars
@app.on_webhook(event_type="file.ready", secret=os.environ["FILE_READY_WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File ready: {event.resource_id}")
    await process_file(event.resource_id)

@app.on_webhook(event_type="comment.created", secret=os.environ["COMMENT_CREATED_WEBHOOK_SECRET"])
async def on_comment_created(event: WebhookEvent):
    print(f"New comment: {event.resource_id}")
    await notify_team(event)

@app.on_webhook(event_type="comment.updated", secret=os.environ["COMMENT_UPDATED_WEBHOOK_SECRET"])
async def on_comment_updated(event: WebhookEvent):
    print(f"Updated comment: {event.resource_id}")
    await notify_team(event)
```

## Example 3: Using the API Client

```python
import os
from frameio import CreateCommentParamsData
from frameio_kit import App, WebhookEvent, Message

app = App(token=os.getenv("FRAMEIO_TOKEN"))

# Single webhook - use default WEBHOOK_SECRET
@app.on_webhook("file.ready")
async def add_processing_comment(event: WebhookEvent):
    # Use the API client to add a comment back to Frame.io
    await app.client.comments.create(
        account_id=event.account_id,
        file_id=event.resource_id,
        data=CreateCommentParamsData(text="File has been automatically processed!")
    )
```

## Dynamic Secret Resolution

When you need to resolve webhook secrets dynamically (e.g., from a database for multi-tenant applications), use secret resolvers.

### Decorator-Level Resolver

Provide an async function that receives the [`WebhookEvent`](../api_reference.md#frameio_kit.WebhookEvent) and returns the secret:

```python
from frameio_kit import App, WebhookEvent

app = App()

async def resolve_webhook_secret(event: WebhookEvent) -> str:
    """Resolve secret based on account ID."""
    return await db.get_webhook_secret(account_id=event.account_id)

# Use the resolver for this specific webhook
@app.on_webhook("file.ready", secret=resolve_webhook_secret)
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready")
```

### Secret Resolution Precedence

1. Explicit string secret (`secret="..."`)
2. Decorator-level resolver (`secret=my_resolver`)
3. Install system resolver (when `install=True`, secrets are auto-managed)
4. Environment variable (`WEBHOOK_SECRET`)

## Setting Up Webhooks in Frame.io

See [Webhook Tutorial](https://developer.staging.frame.io/platform/docs/guides/webhooks#webhook-tutorial) for instructions on how to set up webhooks in Frame.io.

## Best Practices

1. **Handle errors gracefully** - Webhook failures can cause retries
2. **Keep handlers fast** - Long-running operations should be queued, Frame.io expects a response within 5 seconds
3. **Handle retries** - Non-2xx or slow responses will cause Frame.io to retry the request up to 5 times (initial + 4 retries)
4. **Log webhook events** for debugging and monitoring

## Security Considerations

- **Use HTTPS** for your webhook endpoints
- **Validate event data** before processing
- **Implement rate limiting** to prevent abuse
- **Monitor for suspicious activity** and unexpected payloads
