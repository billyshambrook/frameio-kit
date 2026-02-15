# Client API

The Frame.io API client allows you to make authenticated calls back to the Frame.io API from within your handlers. This enables you to fetch data, create resources, and interact with Frame.io programmatically.

## Why Use the API Client?

The API client is essential when you need to:

- **Fetch additional data** about files, projects, or users
- **Create resources** like comments, annotations, or tasks
- **Update existing data** in Frame.io
- **Integrate with Frame.io's full feature set** beyond webhooks and actions
- **Build comprehensive workflows** that interact with Frame.io data

## How the API Client Works

1. **Initialize with token** - Provide a Frame.io API token when creating your `App`
2. **Access via `app.client`** - The client is available as a property on your app instance
3. **Make async calls** - All API methods are asynchronous and must be awaited
4. **Handle responses** - API calls return structured data that you can process

```
Your Handler → app.client → Frame.io API → Response Data
```

## Initialization

Initialize the client by providing a Frame.io API token:

```python
import os
from frameio_kit import App

# Initialize with API token
app = App(token=os.getenv("FRAMEIO_TOKEN"))

# Client is now available at app.client
```

### Getting an API Token

Follow the [Server to Server Authentication](https://next.developer.frame.io/platform/docs/guides/authentication#server-to-server-authentication) guide to get an access token.

## Available Resources

The client organizes Frame.io API endpoints into resource namespaces:

| Resource | Description | Example |
|----------|-------------|---------|
| `app.client.files` | File operations (show, list, upload) | `app.client.files.show(...)` |
| `app.client.comments` | Create and manage comments | `app.client.comments.create(...)` |
| `app.client.projects` | Project operations | `app.client.projects.show(...)` |
| `app.client.workspaces` | Workspace operations | `app.client.workspaces.show(...)` |
| `app.client.users` | User profile operations | `app.client.users.show()` |

For the full list of endpoints and parameters, see the Python examples in Frame.io's [API Reference](https://next.developer.frame.io/platform/api-reference/account-permissions/index).

## Example: File Processing with Comments

```python
import os
from frameio_kit import App, WebhookEvent, Message
from frameio import CreateCommentParamsData

app = App(token=os.getenv("FRAMEIO_TOKEN"))

@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def process_file(event: WebhookEvent):
    # Get file details
    file = await app.client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )
    print(f"Processing: {file.data.name}")

    # Simulate processing
    await process_file_content(file)

    # Add a comment to the file
    await app.client.comments.create(
        account_id=event.account_id,
        file_id=event.resource_id,
        data=CreateCommentParamsData(text="File processed successfully!")
    )

async def process_file_content(file):
    # Your processing logic here
    pass
```

## Error Handling

API calls can fail for various reasons. The `frameio` SDK raises `httpx.HTTPStatusError` for non-2xx responses:

```python
import httpx
from frameio import CreateCommentParamsData

@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    try:
        file = await app.client.files.show(
            account_id=event.account_id,
            file_id=event.resource_id,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # File was deleted before we could process it
            return
        raise  # Re-raise unexpected errors
```

Common status codes to handle:

| Status | Meaning | Recommended Action |
|--------|---------|-------------------|
| 401 | Token expired or invalid | Check token configuration |
| 404 | Resource not found (deleted) | Skip processing gracefully |
| 429 | Rate limit exceeded | Back off and retry |

## Best Practices

1. **Always use `await`** — all API calls are asynchronous
2. **Handle errors** — especially 404 (resource deleted) and 429 (rate limit)
3. **Use appropriate permissions** — ensure your token has the required scopes
4. **Cache when possible** — avoid repeated calls for the same data
5. **Respect rate limits** — Frame.io has API rate limits
6. **Use environment variables** for tokens and sensitive data

## Experimental API

Access experimental features via `app.client.experimental`:

```python
# Experimental custom actions API
actions = await app.client.experimental.custom_actions.actions_index(
    account_id=event.account_id,
    workspace_id=event.workspace_id,
)
```

**Note**: Experimental APIs may change without notice. Use with caution in production.

## Authentication

### Server-to-Server Authentication (Default)

The client automatically handles authentication using your provided token. No additional setup is required - just make sure your token has the necessary permissions for the operations you want to perform.

```python
app = App(token=os.getenv("FRAMEIO_TOKEN"))

# Use app.client for S2S authenticated calls
file = await app.client.files.show(...)
```

### User Authentication

For user-specific authentication, you can create a client with a user's OAuth token. This attributes API calls to the user in Frame.io activity logs.

```python
from frameio_kit import Client, get_user_token

@app.on_action(..., require_user_auth=True)
async def my_action(event: ActionEvent):
    # Create client with user's token from context
    async with Client(token=get_user_token()) as user_client:
        # API calls are now attributed to the user
        file = await user_client.files.show(...)
```

See the [User Authentication guide](user-auth.md) for details on enabling Adobe Login OAuth.

### Per-Tenant Client (Multi-Tenant Apps)

If each tenant provides their own API token (e.g., via [custom install fields](self-service-install.md#custom-install-fields)), create a client with the tenant's token:

```python
from frameio_kit import Client, get_install_config

@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    config = get_install_config()
    async with Client(token=config["api_token"]) as tenant_client:
        file = await tenant_client.files.show(
            account_id=event.account_id,
            file_id=event.resource_id,
        )
```
