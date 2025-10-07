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
@app.on_action(
    event_type="my_app.analyze",
    name="Analyze File", 
    description="Perform analysis on this file",
    secret="your-secret"
)
async def analyze_file(event: ActionEvent):
    # Handle the action
    pass
```

### Parameters

- [`event_type`](../api_reference.md#frameio_kit.App.on_action\(event_type\)) *(str)*: Unique identifier for this action
- [`name`](../api_reference.md#frameio_kit.App.on_action\(name\)) *(str)*: Display name in Frame.io UI
- [`description`](../api_reference.md#frameio_kit.App.on_action\(description\)) *(str)*: Description shown in UI
- [`secret`](../api_reference.md#frameio_kit.App.on_action\(secret\)) *(str)*: Signing secret from Frame.io

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

## Example 1: Simple Message

```python
import os
from frameio_kit import App, ActionEvent, Message

app = App()

@app.on_action(
    event_type="asset.notify",
    name="Notify Team",
    description="Send notification about this asset",
    secret=os.environ["ACTION_SECRET"]
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

## Example 2: Form with Input

```python
import os
from frameio_kit import App, ActionEvent, Message, Form, TextField, SelectField, SelectOption

app = App()

PLATFORMS = [
    SelectOption(name="Twitter", value="twitter"),
    SelectOption(name="Instagram", value="instagram"),
]

@app.on_action(
    event_type="asset.publish",
    name="Publish Asset",
    description="Publish this asset to social media",
    secret=os.environ["ACTION_SECRET"]
)
async def publish_asset(event: ActionEvent):
    # Step 2: Form submitted, process the data
    if event.data:
        platform = event.data.get("platform")
        caption = event.data.get("caption")
        
        print(f"Publishing to {platform}: {caption}")
        # Process the publication here
        
        return Message(
            title="Published!",
            description=f"Asset published to {platform} successfully."
        )
    
    # Step 1: Show the form
    return Form(
        title="Publish to Social Media",
        description="Configure your post:",
        fields=[
            SelectField(label="Platform", name="platform", options=PLATFORMS),
            TextField(label="Caption", name="caption", placeholder="Enter your caption...")
        ]
    )
```

## Example 3: Complex Form

```python
import datetime
from frameio_kit import App, ActionEvent, Message, Form, TextField, TextareaField, CheckboxField, DateField

app = App()

@app.on_action(
    event_type="asset.schedule",
    name="Schedule Review",
    description="Schedule a review for this asset",
    secret=os.environ["ACTION_SECRET"]
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
