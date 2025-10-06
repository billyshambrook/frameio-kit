# Handling Custom Actions

Custom Actions are user-triggered menu items in the Frame.io UI. They are perfect for building interactive workflows that can present information, ask for user input, and perform tasks on demand.

Use the `@app.on_action` decorator to register a handler for a custom action.

## Decorator Arguments

- `event_type` *(str)*: A unique string you define to identify this action (e.g., `"my_app.transcribe"`). This is the type that will be present in the incoming payload.
- `name` *(str)*: The user-visible name for the action in the Frame.io UI menu.
- `description` *(str)*: A short, user-visible description of what the action does.
- `secret` *(str)*: The mandatory signing secret generated when you create the custom action in Frame.io.


## Responding to Actions

Every action handler must return a response object that Frame.io can render in the UI. `frameio-kit` provides two response types:

- `Message`: To display a simple notification or confirmation to the user.
- `Form`: To present a modal with input fields to collect information from the user.

### Displaying a `Message`

A `Message` is the simplest way to provide feedback. It's ideal for actions that complete a task in a single step and don't require further user input.

The `Message` object takes two arguments:

- `title` *(str)*: The header text of the message.
- `description` *(str)*: The body text of the message.

### Example: Notifying an Administrator

This action simulates sending a notification and then confirms to the user that the action was successful.

```python
from frameio_kit import App, ActionEvent, Message

app = App()

@app.on_action(
    event_type="asset.notify_admin",
    name="Notify Admin",
    description="Send a notification to the admin about this asset.",
    secret="your-secret"
)
async def notify_admin(event: ActionEvent):
    # In a real application, you would add logic here to send an email or Slack message.
    print(f"Notification triggered for asset {event.resource_id} by user {event.user.id}")

    return Message(
        title="Admin Notified",
        description=f"A notification for asset '{event.resource.name}' has been sent."
    )
```

### Requesting Input with a `Form`

The real power of Custom Actions lies in their ability to create interactive, multi-step workflows. You can request input by returning a `Form` object from your handler.

This initiates a two-step process:

1. Initial Request: The user clicks the action. Your handler is called with no form data (`event.data` is `None`). You return a `Form` object defining the fields you want to display. Frame.io renders this as a modal.
2. Submission Request: The user fills out the form and clicks "Submit". Your same handler is called again, but this time `event.data` is a dictionary containing the submitted values. You process this data and return a `Message` to confirm completion.

A `Form` object takes the following arguments:

- `title` *(str)*: The title displayed at the top of the form modal.
- `description` *(str)*: Explanatory text displayed below the title.
- `fields` *(list)*: A list of field objects to render in the form.

### Form Field Examples

Here are small, focused examples of how to use each field type within a `Form`.

#### `TextField`

For capturing a single line of text, like a title or a name.

```python
from frameio_kit import Form, TextField

# Assumes this is returned from inside an @app.on_action handler
return Form(
    title="Rename Asset",
    fields=[
        TextField(label="New Asset Name", name="asset_name", value=event.resource.name)
    ]
)
```

#### `TextareaField`

For capturing longer, multi-line text, such as comments or descriptions.

```python
from frameio_kit import Form, TextareaField

return Form(
    title="Add a Comment",
    fields=[
        TextareaField(label="Comment", name="comment_text", placeholder="Enter your feedback...")
    ]
)
```

#### `SelectField`

For allowing the user to choose one option from a predefined list.

```python
from frameio_kit import Form, SelectField, SelectOption

PLATFORMS = [
    SelectOption(name="Twitter", value="twitter"),
    SelectOption(name="Instagram", value="instagram"),
]

return Form(
    title="Choose Platform",
    fields=[
        SelectField(label="Platform", name="platform", options=PLATFORMS, value="twitter")
    ]
)
```

#### `CheckboxField`

For a simple boolean toggle, like a "yes/no" or "on/off" choice.

```python
from frameio_kit import Form, CheckboxField

return Form(
    title="Confirm Action",
    fields=[
        CheckboxField(label="Overwrite existing file?", name="overwrite", value=False)
    ]
)
```

#### `DateField`

For allowing the user to select a date from a calendar picker.

```python
import datetime
from frameio_kit import Form, DateField

return Form(
    title="Set Due Date",
    fields=[
        DateField(label="Due Date", name="due_date", value=datetime.date.today().isoformat())
    ]
)
```

### Comprehensive Example: Publishing to Social Media

This example demonstrates how to combine all available form fields into a single, practical workflow.

```python
import datetime
from frameio_kit import (
    App,
    ActionEvent,
    Message,
    Form,
    TextField,
    DateField,
    TextareaField,
    CheckboxField,
    SelectField,
    SelectOption,
)

app = App()

PLATFORMS = [
    SelectOption(name="Twitter", value="twitter"),
    SelectOption(name="Instagram", value="instagram"),
    SelectOption(name="LinkedIn", value="linkedin"),
]

@app.on_action(event_type="asset.publish_social", name="Publish to Social Media", secret="your-secret")
async def on_publish(event: ActionEvent):
    # Step 2: Form has been submitted, process the data.
    if event.data:
        platform = event.data.get("platform")
        title = event.data.get("title")
        publish_now = event.data.get("publish_now")
        schedule_date = event.data.get("schedule_date")

        publish_time = "immediately" if publish_now else f"on {schedule_date}"

        print(f"Scheduling post '{title}' for {platform} to be published {publish_time}.")
        # Here you would typically trigger a publishing workflow.

        return Message(
            title="Post Scheduled",
            description=f"Your post '{title}' is scheduled to be published to {platform} {publish_time}."
        )

    # Step 1: No form data, so display the initial form.
    return Form(
        title="Publish to Social Media",
        description="Configure the details for your social media post.",
        fields=[
            SelectField(label="Platform", name="platform", options=PLATFORMS, value="twitter"),
            TextField(label="Post Title", name="title", value=event.resource.name),
            TextareaField(label="Description", name="description", placeholder="Enter post description..."),
            CheckboxField(label="Publish Immediately", name="publish_now", value=True),
            DateField(label="Schedule Date", name="schedule_date", value=datetime.date.today().isoformat()),
        ]
    )
```
