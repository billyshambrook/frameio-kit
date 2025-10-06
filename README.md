# frameio-kit: The Python Framework for Building Frame.io Apps

frameio-kit is a modern, asynchronous Python framework for building robust and scalable integrations with Frame.io. It handles the complex plumbing of webhooks, custom actions, and authentication, allowing you to focus on your application's unique business logic.

```python
import os

import uvicorn
from frameio_kit import ActionEvent, App, Message, WebhookEvent

app = App()

@app.on_webhook(event_type="file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    """Runs when a file finishes transcoding."""
    print(f"Received event for file: {event.resource_id}")


@app.on_action(event_type="greeting", name="Greeting", secret=os.environ["ACTION_SECRET"])
async def on_greeting(event: ActionEvent):
    """Says hello"""
    return Message(title="Greeting", description="Hello, world!")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

## Installation

We recommend using [uv](https://docs.astral.sh/uv/) to install and manage frameio-kit.

To add frameio-kit to your project, run:

```bash
uv add frameio-kit
```

Alternatively, you can install it directly with pip:
```bash
pip install frameio-kit
```


## 🎣 Handling Webhooks

Webhooks are automated, non-interactive messages from Frame.io. Use the @app.on_webhook decorator to handle them.

- `event_type`: The event name (e.g., `"comment.created"`) or a list of names.
- `secret`: The signing secret from your webhook's settings.

Example:
```python
from frameio_kit import App, Message, WebhookEvent

app = App()

@app.on_webhook("comment.created", secret=os.environ["WEBHOOK_SECRET"])
async def on_new_asset(event: WebhookEvent):
    print(f"Comment '{event.resource_id}' was created.")
```

## 🎬 Handling Custom Actions

Custom Actions are user-triggered menu items in the UI, perfect for interactive workflows. Use the @app.on_action decorator.

The key feature is returning a Form to ask the user for input. When the user submits the form, your handler is called a second time with the form data in event.data.

### Example: A Two-Step Transcription Action

#### Step 1: Present a Form to the User

First, define a handler that returns a Form when the user clicks the action.

```python
from frameio_kit import Form, SelectField, SelectOption

LANGUAGES = [SelectOption(name=lang, value=val) for lang, val in [("English", "en"), ("Spanish", "es")]]

@app.on_action(event_type="transcribe.file", name="Transcribe")
async def on_transcribe(event: ActionEvent):
    # If event.data exists, the form was submitted. We'll handle that next.
    if event.data:
        # ... handle form data ...
        pass

    # Initially, just return the form to ask for input.
    return Form(
        title="Choose Language",
        description="Select the language for transcription.",
        fields=[SelectField(label="Language", name="language", options=LANGUAGES)]
    )
```

#### Step 2: Handle the Form Submission

Now, add the logic to handle the submission inside the same function.

```python
@app.on_action(...)
async def on_transcribe(event: ActionEvent):
    # This block now executes on the second request
    if event.data:
        language = event.data.get("language")
        print(f"Transcribing {event.resource_id} in '{language}'...")
        return Message(title="In Progress", description=f"Transcription started.")

    # ... code to return the initial form ...

```

## 🌐 Using the API Client

To make calls back to the Frame.io API, initialize `App` with an `token`.

```python
app = App(token=os.getenv("FRAMEIO_TOKEN"))
```

The client is available at `app.client` and provides access to both stable and experimental endpoints.

- **Stable API**: `app.client.http`
- **Experimental API**: `app.client.experimental.http`

### Example: Add a Comment to a File

This example uses the stable API to post a comment to a file after it's processed.

```python
from frameio import CreateCommentParamsData

@app.on_webhook(...)
async def add_confirmation_comment(event: WebhookEvent):
    """Adds a comment to the file after it's processed."""
    response = await app.client.comments.create(
        account_id=event.account_id,
        file_id=event.resource_id,
        data=CreateCommentParamsData(text="Processed by our automation server."),
    )
    print("Successfully added comment: ", response.data.id)
```


## Contributing

Contributions are the core of open source! We welcome improvements and features.

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

### Setup

1. Clone the repository:

```bash
git clone https://github.com/billyshambrook/frameio-kit.git
cd frameio-kit
```

2. Create and sync the environment:

```bash
uv sync
```

This installs all dependencies, including dev tools.

3. Activate the virtual environment (e.g., `source .venv/bin/activate` or via your IDE).

### Unit Tests

frameio-kit uses pytest for testing. To run the tests, run:

```bash
uv run pytest
```

### Static Checks

frameio-kit uses `pre-commit` for code formatting, linting and type checking.

Install the pre-commit hooks:

```bash
uv run pre-commit install
```

The hooks will run on every commit. You can also run them manually:

```bash
uv run pre-commit run --all-files
```

### Pull Requests

1. Fork the repository on GitHub.
2. Create a feature branch from main.
3. Make your changes, including tests and documentation updates.
4. Ensure tests and pre-commit hooks pass.
5. Commit your changes and push to your fork.
6. Open a pull request against the main branch of billyshambrook/frameio-kit.

Please open an issue or discussion for questions or suggestions before starting significant work!
