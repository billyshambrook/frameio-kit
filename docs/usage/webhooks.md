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
@app.on_webhook(event_type="file.ready", secret="your-secret")
async def on_file_ready(event: WebhookEvent):
    # Handle the event
    pass
```

### Parameters

- [`event_type`](../api_reference.md#frameio_kit.App.on_webhook\(event_type\)) *(str | list[str])*: The event name(s) to listen for
- [`secret`](../api_reference.md#frameio_kit.App.on_webhook\(secret\)) *(str)*: The signing secret from Frame.io (required for security)

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

## Common Event Types

Frame.io supports many webhook events. Here are the most commonly used:

| Event Type | Triggered When |
|------------|----------------|
| `file.ready` | File finishes processing and is ready for viewing |
| `file.created` | New file is uploaded |
| `file.deleted` | File is deleted |
| `comment.created` | New comment is added to a file |
| `comment.updated` | Comment is edited |
| `review_link.created` | New review link is generated |
| `project.created` | New project is created |

For the complete list, see Frame.io's [Webhook Event Subscriptions](https://developer.staging.frame.io/platform/docs/guides/webhooks#webhook-event-subscriptions) documentation.

## Example 1: File Processing

```python
import os
from frameio_kit import App, WebhookEvent, Message

app = App()

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready for processing")
    
    # Simulate some processing
    await process_file(event.resource_id)

async def process_file(file_id: str):
    # Your processing logic here
    pass
```

## Example 2: Multiple Event Types

```python
from frameio_kit import App, WebhookEvent

app = App()

@app.on_webhook(
    event_type=["comment.created", "comment.updated"], 
    secret=os.environ["WEBHOOK_SECRET"]
)
async def on_comment_change(event: WebhookEvent):
    action = "created" if event.type == "comment.created" else "updated"
    print(f"Comment {action}: {event.resource_id}")
    
    # Send notification to team
    await notify_team(event)
```

## Example 3: Using the API Client

```python
import os
from frameio import CreateCommentParamsData
from frameio_kit import App, WebhookEvent, Message

app = App(token=os.getenv("FRAMEIO_TOKEN"))

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def add_processing_comment(event: WebhookEvent):
    # Use the API client to add a comment back to Frame.io
    await app.client.comments.create(
        account_id=event.account_id,
        file_id=event.resource_id,
        data=CreateCommentParamsData(text="File has been automatically processed!")
    )
```

## Configuration

To set up webhooks in Frame.io:

1. Navigate to **Workspace Settings → Webhooks**
2. Click **"Create Webhook"**
3. Select the event types to subscribe to
4. Enter your webhook URL
5. Copy the signing secret and add it to your application

For detailed instructions, see Frame.io's [Webhook Tutorial](https://developer.staging.frame.io/platform/docs/guides/webhooks#webhook-tutorial).

## Best Practices

**Response Timeout**

Frame.io expects a response within **5 seconds**. For long-running operations, queue the work and return immediately:

```python
@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    # Queue the work for background processing
    await task_queue.enqueue(process_file, event.resource_id)
    # Return immediately
```

**Handle Retries**

Frame.io retries failed webhooks up to 5 times (initial request + 4 retries). Make your handlers idempotent to safely handle duplicate events.

**Error Handling**

Return appropriate HTTP status codes:
- **200-299**: Success - no retry
- **400-499**: Client error - no retry
- **500-599**: Server error - triggers retry

**Logging**

Log all webhook events for debugging and monitoring. Include the event type, resource ID, and processing result.

## Security

- **HTTPS only** - Use HTTPS in production (Frame.io enforces this)
- **Signature verification** - Automatically handled by frameio-kit
- **Rate limiting** - Implement limits to prevent abuse
- **Validation** - Validate event data before processing
