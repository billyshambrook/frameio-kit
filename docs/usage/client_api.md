# Client API

The Frame.io API client enables you to make authenticated calls to Frame.io's REST API from within your handlers. Use it to fetch data, create resources, and build comprehensive workflows.

## When to Use the Client

Use the API client when you need to:

- Fetch file, project, or user data
- Create comments, annotations, or tasks
- Update resources in Frame.io
- Build workflows that interact with Frame.io data

## Quick Example

```python
import os
from frameio_kit import App, WebhookEvent
from frameio import CreateCommentParamsData

app = App(token=os.getenv("FRAMEIO_TOKEN"))

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def process_file(event: WebhookEvent):
    # Get file details
    file = await app.client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )

    # Add a comment
    await app.client.comments.create(
        account_id=event.account_id,
        file_id=event.resource_id,
        data=CreateCommentParamsData(text=f"Processing {file.data.name}...")
    )
```

## Setup

### Get an API Token

Follow Frame.io's [Server to Server Authentication](https://developer.staging.frame.io/platform/docs/guides/authentication#server-to-server-authentication) guide to obtain an access token.

### Initialize with Token

```python
import os
from frameio_kit import App

app = App(token=os.getenv("FRAMEIO_TOKEN"))
```

The client is automatically available at `app.client` with your token configured.

## Available Endpoints

The client provides access to all Frame.io API endpoints. See Frame.io's [API Reference](https://developer.staging.frame.io/platform/api-reference/account-permissions/index) for the complete list of available methods and Python examples.

Common endpoints include:

- **Files**: `app.client.files.*`
- **Comments**: `app.client.comments.*`
- **Projects**: `app.client.projects.*`
- **Teams**: `app.client.teams.*`
- **Users**: `app.client.users.*`

All methods are async and must be awaited.

## Authentication Methods

### Server-to-Server (Default)

API calls use your application token automatically:

```python
app = App(token=os.getenv("FRAMEIO_TOKEN"))

# API calls use your application token
file = await app.client.files.show(...)
```

### User Authentication

For user-specific operations, create a client with the user's OAuth token:

```python
from frameio_kit import Client

@app.on_action(..., require_user_auth=True)
async def my_action(event: ActionEvent):
    # Create client with user's token
    user_client = Client(token=event.user_access_token)

    # API calls are attributed to the user
    file = await user_client.files.show(...)

    await user_client.close()
```

See the [User Authentication guide](user_auth.md) for setup instructions.

## Experimental Features

Access experimental APIs via `app.client.experimental`:

```python
actions = await app.client.experimental.actions.actions_index(
    account_id=event.account_id,
    workspace_id=event.workspace_id
)
```

**Warning**: Experimental APIs may change without notice. Avoid using in production.

## Best Practices

**Always await API calls** - All methods are async

**Handle errors gracefully** - Network issues and API errors can occur

**Cache when appropriate** - Avoid repeated calls for the same data

**Check token permissions** - Ensure your token has required scopes for the operations you need

**Respect rate limits** - Frame.io enforces API rate limits

**Close user clients** - Always call `await user_client.close()` when using user-specific clients
