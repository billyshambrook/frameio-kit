# Custom Actions

Custom Actions are user-triggered menu items in the Frame.io UI. They're perfect for building interactive workflows that can present information, ask for user input, and perform tasks on demand.

## Why Use Custom Actions?

Custom Actions are ideal when you need to:

- **Build interactive workflows** that require user input
- **Create on-demand tools** for specific tasks
- **Integrate external services** with Frame.io assets
- **Automate complex processes** with user guidance
- **Provide contextual actions** based on the selected asset

## How Custom Actions Work

1. **User clicks action** in the Frame.io UI (right-click menu, toolbar, etc.)
2. **Your handler is called** with the action event
3. **Return a response** - either a [`Message`](../api_reference.md#frameio_kit.Message) for simple feedback or a [`Form`](../api_reference.md#frameio_kit.Form) for user input
4. **If Form returned** - user fills it out and submits, your handler is called again with the form data

```
User Click → Handler → Message (done) OR Form → User Input → Handler → Message
```

## Action Decorator

Use the [`@app.on_action`](../api_reference.md#frameio_kit.App.on_action) decorator to register handlers:

```python
import os

# Single action - use default CUSTOM_ACTION_SECRET env var
@app.on_action(
    event_type="my_app.analyze",
    name="Analyze File",
    description="Perform analysis on this file"
)
async def analyze_file(event: ActionEvent):
    # Handle the action
    pass

# Multiple actions with different secrets - use explicit env vars
@app.on_action(
    event_type="my_app.analyze",
    name="Analyze File",
    description="Perform analysis on this file",
    secret=os.environ["ANALYZE_CUSTOM_ACTION_SECRET"]
)
async def analyze_file(event: ActionEvent):
    pass

@app.on_action(
    event_type="my_app.transcribe",
    name="Transcribe",
    description="Transcribe this file",
    secret=os.environ["TRANSCRIBE_CUSTOM_ACTION_SECRET"]
)
async def transcribe_file(event: ActionEvent):
    pass
```

### Parameters

- [`event_type`](../api_reference.md#frameio_kit.App.on_action\(event_type\)) *(str)*: Unique identifier for this action
- [`name`](../api_reference.md#frameio_kit.App.on_action\(name\)) *(str)*: Display name in Frame.io UI
- [`description`](../api_reference.md#frameio_kit.App.on_action\(description\)) *(str)*: Description shown in UI
- [`secret`](../api_reference.md#frameio_kit.App.on_action\(secret\)) *(str | None, optional)*: Signing secret from Frame.io. If not provided, falls back to the `CUSTOM_ACTION_SECRET` environment variable. Explicit parameter takes precedence over environment variable.
- [`require_user_auth`](../api_reference.md#frameio_kit.App.on_action\(require_user_auth\)) *(bool, optional)*: Require user to authenticate via Adobe Login OAuth. When `True`, users must sign in before the action executes. See [User Authentication](user_auth.md) for details.

!!! note "Environment Variables"
    **Single action:** Use the default `CUSTOM_ACTION_SECRET` environment variable and omit the `secret` parameter.

    **Multiple actions with different secrets:** Pass each secret explicitly via `secret=os.environ["ACTION_NAME_CUSTOM_ACTION_SECRET"]` to keep secrets out of your code while supporting multiple action configurations.

## Action Event Object

The [`ActionEvent`](../api_reference.md#frameio_kit.ActionEvent) object provides access to action data:

```python
from frameio_kit import ActionEvent

async def handler(event: ActionEvent):
    print(event.type)           # "my_app.analyze"
    print(event.resource_id)    # "abc123"
    print(event.user.id)        # "user_789"
    print(event.user.name)      # "John Doe"
    print(event.data)           # None (first call) or dict (form submission)
```

## Response Types

Custom Actions support two response types:

### [`Message`](../api_reference.md#frameio_kit.Message) - Simple Feedback

For actions that complete immediately without user input:

```python
from frameio_kit import Message

return Message(
    title="Task Complete",
    description="Your file has been processed successfully!"
)
```

### [`Form`](../api_reference.md#frameio_kit.Form) - User Input

For actions that need user input:

```python
from frameio_kit import Form, TextField

return Form(
    title="Configure Settings",
    description="Enter your preferences:",
    fields=[
        TextField(label="Name", name="name", value="default")
    ]
)
```

## Form Fields

| Field Type | Use Case | Example |
|------------|----------|---------|
| [`TextField`](../api_reference.md#frameio_kit.TextField) | Single line text | Names, titles, IDs |
| [`TextareaField`](../api_reference.md#frameio_kit.TextareaField) | Multi-line text | Comments, descriptions |
| [`SelectField`](../api_reference.md#frameio_kit.SelectField) | Choose from options | Categories, platforms |
| [`CheckboxField`](../api_reference.md#frameio_kit.CheckboxField) | Checkbox toggle | Yes/no, enable/disable |
| [`LinkField`](../api_reference.md#frameio_kit.LinkField) | URL link | External resources |

## Example 1: Single Action (Default Env Var)

```python
from frameio_kit import App, ActionEvent, Message

app = App()

# Single action - CUSTOM_ACTION_SECRET env var used automatically
@app.on_action(
    event_type="asset.notify",
    name="Notify Team",
    description="Send notification about this asset"
)
async def notify_team(event: ActionEvent):
    print(f"Notification sent for {event.resource_id} by {event.user.name}")

    # Send actual notification here
    await send_notification(event.resource_id, event.user.id)

    return Message(
        title="Notification Sent",
        description="Your team has been notified about this asset."
    )
```

## Example 2: Multiple Actions (Explicit Env Vars)

```python
import os
from frameio_kit import App, ActionEvent, Message, Form, TextField, SelectField, SelectOption

app = App()

PLATFORMS = [
    SelectOption(name="Twitter", value="twitter"),
    SelectOption(name="Instagram", value="instagram"),
]

# Multiple actions with different secrets - use explicit env vars
@app.on_action(
    event_type="asset.publish",
    name="Publish Asset",
    description="Publish this asset to social media",
    secret=os.environ["PUBLISH_CUSTOM_ACTION_SECRET"]
)
async def publish_asset(event: ActionEvent):
    if event.data:
        platform = event.data.get("platform")
        caption = event.data.get("caption")
        print(f"Publishing to {platform}: {caption}")
        return Message(title="Published!", description=f"Asset published to {platform} successfully.")

    return Form(
        title="Publish to Social Media",
        description="Configure your post:",
        fields=[
            SelectField(label="Platform", name="platform", options=PLATFORMS),
            TextField(label="Caption", name="caption", placeholder="Enter your caption...")
        ]
    )

@app.on_action(
    event_type="asset.analyze",
    name="Analyze Asset",
    description="Perform AI analysis on this asset",
    secret=os.environ["ANALYZE_CUSTOM_ACTION_SECRET"]
)
async def analyze_asset(event: ActionEvent):
    # Perform analysis
    analysis_result = await perform_analysis(event.resource_id)

    return Message(
        title="Analysis Complete",
        description=f"Analysis score: {analysis_result}"
    )
```

## Example 3: Complex Form

```python
import os
import datetime
from frameio_kit import App, ActionEvent, Message, Form, TextField, TextareaField, CheckboxField, DateField

app = App()

# Single action - use default CUSTOM_ACTION_SECRET
@app.on_action(
    event_type="asset.schedule",
    name="Schedule Review",
    description="Schedule a review for this asset"
)
async def schedule_review(event: ActionEvent):
    if event.data:
        reviewer = event.data.get("reviewer")
        due_date = event.data.get("due_date")
        urgent = event.data.get("urgent", False)
        notes = event.data.get("notes", "")

        priority = "urgent" if urgent else "normal"
        print(f"Scheduling {priority} review with {reviewer} by {due_date}")

        return Message(
            title="Review Scheduled",
            description=f"Review assigned to {reviewer} for {due_date}"
        )

    return Form(
        title="Schedule Review",
        description="Set up a review for this asset:",
        fields=[
            TextField(label="Reviewer Email", name="reviewer", placeholder="reviewer@company.com"),
            DateField(label="Due Date", name="due_date", value=datetime.date.today().isoformat()),
            CheckboxField(label="Urgent", name="urgent", value=False),
            TextareaField(label="Notes", name="notes", placeholder="Additional instructions...")
        ]
    )
```

## Dynamic Secret Resolution

When you need to resolve action secrets dynamically (e.g., from a database for multi-tenant applications), use secret resolvers.

### Decorator-Level Resolver

Provide an async function that receives the [`ActionEvent`](../api_reference.md#frameio_kit.ActionEvent) and returns the secret:

```python
from frameio_kit import App, ActionEvent, Message

app = App()

async def resolve_action_secret(event: ActionEvent) -> str:
    """Resolve secret based on account ID or resource."""
    return await db.get_action_secret(account_id=event.account_id)

# Use the resolver for this specific action
@app.on_action(
    event_type="my_app.process",
    name="Process File",
    description="Process this file",
    secret=resolve_action_secret
)
async def process_file(event: ActionEvent):
    return Message(title="Processing", description="File is being processed")
```

### App-Level Resolver

For centralized secret management across all actions, use the app-level resolver. See [App Configuration](app.md#dynamic-secret-resolution) for details:

```python
from frameio_kit import App, SecretResolver, WebhookEvent, ActionEvent

class MySecretResolver:
    async def get_webhook_secret(self, event: WebhookEvent) -> str:
        return await db.get_webhook_secret(event.account_id)

    async def get_action_secret(self, event: ActionEvent) -> str:
        return await db.get_action_secret(event.account_id)

app = App(secret_resolver=MySecretResolver())

# All actions use the app-level resolver by default
@app.on_action(
    event_type="my_app.process",
    name="Process File",
    description="Process this file"
)
async def process_file(event: ActionEvent):
    return Message(title="Processing", description="File is being processed")
```

### Secret Resolution Precedence

1. Explicit string secret (`secret="..."`)
2. Decorator-level resolver (`secret=my_resolver`)
3. App-level resolver (`App(secret_resolver=...)`)
4. Environment variable (`CUSTOM_ACTION_SECRET`)

## Setting Up Custom Actions in Frame.io

1. **Go to Workspace Settings** in Frame.io
2. **Navigate to Actions** section  
3. **Create a new Custom Action**:
   - Name: Display name in UI
   - Description: What the action does
   - Event: Must match your `event_type` parameter
   - URL: Your application's public endpoint
   - Secret: Copy the generated secret to your environment variables
4. **Test the action** by right-clicking on an asset

## Best Practices

1. **Keep actions focused** - Each action should do one thing well
2. **Provide clear feedback** - Use descriptive titles and messages
3. **Handle form validation** - Check required fields and provide helpful errors
4. **Use meaningful names** - Make event types and display names descriptive
5. **Test thoroughly** - Custom actions are user-facing, so they need to work reliably
6. **Consider user experience** - Keep forms simple and intuitive

## Two-Step Process

Custom Actions use a two-step process when returning forms:

1. **Initial call** - `event.data` is `None`, return a `Form`
2. **Form submission** - `event.data` contains the submitted values, return a `Message`

```python
async def my_action(event: ActionEvent):
    if event.data is None:
        # First call - show the form
        return Form(title="My Form", fields=[...])
    else:
        # Second call - process the form data
        return Message(title="Done", description="Form processed!")
```
