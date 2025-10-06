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

## 🔐 OAuth User Authorization

For custom actions that need to act on behalf of a user, frameio-kit provides full OAuth 2.0 support. This allows your app to obtain user tokens and perform actions with user permissions.

### Setting Up OAuth

frameio-kit provides built-in token storage implementations for common backends:

#### Option 1: In-Memory Storage (Development/Testing)

```python
from frameio_kit import App, InMemoryTokenStore

app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri="https://yourapp.com/oauth/callback",
    token_store=InMemoryTokenStore()  # Tokens lost on restart!
)
```

**Note**: InMemoryTokenStore is only suitable for development. All tokens are lost when the app restarts.

#### Option 2: DynamoDB Storage (Production)

```python
from frameio_kit import App, DynamoDBTokenStore

# Create DynamoDB token store
token_store = DynamoDBTokenStore(
    table_name="frameio-user-tokens",
    region_name="us-east-1"
)

app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri="https://yourapp.com/oauth/callback",
    token_store=token_store
)
```

First, create the DynamoDB table:
```bash
aws dynamodb create-table \
    --table-name frameio-user-tokens \
    --attribute-definitions AttributeName=user_id,AttributeType=S \
    --key-schema AttributeName=user_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1
```

#### Option 3: Custom Storage

Implement the `TokenStore` interface for your own database:

```python
from frameio_kit import TokenStore

class CustomTokenStore(TokenStore):
    async def save_token(self, user_id: str, token_data: dict):
        # Save to your database
        pass
    
    async def get_token(self, user_id: str) -> dict | None:
        # Retrieve from your database
        pass
```

### OAuth Flow in Custom Actions

Here's a complete example of a custom action that requires user authorization:

```python
@app.on_action(
    event_type="export.asset",
    name="Export to My Service",
    description="Export this asset to my external service",
    secret=os.getenv("ACTION_SECRET")
)
async def export_asset(event: ActionEvent):
    """Export an asset using user authorization."""
    
    # Check if we have a token for this user
    user_token = await app.oauth.get_user_token(event.user.id)
    
    if not user_token:
        # User needs to authorize - provide them with the authorization URL
        auth_url = app.oauth.get_authorization_url(
            state=f"{event.user.id}:{event.interaction_id}"
        )
        return Message(
            title="Authorization Required",
            description=f"This action requires your authorization. Please visit the following URL to authorize: {auth_url}\n\nAfter authorizing, trigger this action again."
        )
    
    # User is authorized - perform the action on their behalf
    user_client = await app.get_user_client(event.user.id)
    
    # Now you can make API calls as the user
    asset = await user_client.assets.get(
        account_id=event.account_id,
        asset_id=event.resource_id
    )
    
    # Do something with the asset...
    # export_to_external_service(asset)
    
    return Message(
        title="Export Complete",
        description=f"Successfully exported {asset.name}"
    )
```

### How It Works

1. **Initial Request**: When a user triggers the action without authorization, your handler checks for a token and returns a Message with an authorization URL.

2. **User Authorization**: The user visits the authorization URL, approves your app on Frame.io, and is redirected back to your app's OAuth callback endpoint (`/oauth/callback`).

3. **Token Storage**: The callback handler automatically exchanges the authorization code for tokens and stores them using your `TokenStore`.

4. **Subsequent Requests**: The user triggers the action again. This time, your app retrieves their token and creates a user-specific client to perform actions on their behalf.

5. **Token Refresh**: The OAuth manager handles token refresh automatically when tokens expire (developers should implement expiration checking in their `TokenStore`).


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
