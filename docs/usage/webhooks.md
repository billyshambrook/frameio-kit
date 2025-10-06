# Handling Webhooks

Webhooks are automated, non-interactive messages sent from Frame.io to your application when a specific event occurs. They are ideal for workflows that need to react to events in real-time without user intervention.

Use the `@app.on_webhook` decorator to register a handler for one or more webhook events.

## Decorator Arguments

- `event_type` *(str | list[str])*: The event name (e.g., `"file.ready"`) or a list of names to which the handler should subscribe.
- `secret` *(str)*: The signing secret provided by Frame.io when you create the webhook. This is mandatory for security.

## Example: Responding to a New Comment

This example demonstrates how to create a handler that listens for the `comment.created` event and prints the comment's ID.

```python
import os
from frameio_kit import App, WebhookEvent

# It's highly recommended to load secrets from environment variables
app = App()

@app.on_webhook(event_type="comment.created", secret=os.environ["WEBHOOK_SECRET"])
async def on_new_comment(event: WebhookEvent):
    """
    This handler is triggered whenever a new comment is created in the
    configured workspace.
    """
    print(f"A new comment was created with ID: {event.resource_id}")
    print(f"Project ID: {event.project.id}")
    print(f"User who commented: {event.user.id}")
```

The `event` object passed to the handler is a `WebhookEvent` instance, which is a Pydantic model containing the parsed JSON payload from Frame.io. This gives you full type-hinting and validation for all incoming data.

