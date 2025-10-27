# User Authentication with Adobe Login

By default, Frame.io apps use server-to-server (S2S) authentication with an application token. However, some use cases require user-specific authentication to attribute API calls to individual users in Frame.io's activity logs.

The `frameio-kit` library provides built-in support for Adobe Login OAuth 2.0 authentication, allowing users to sign in and authorize your app to make API calls on their behalf.

## When to Use User Authentication

Use user authentication when you need to:

- **Attribute actions to specific users** in Frame.io activity logs
- **Access user-specific resources** that require user permissions
- **Perform actions as the authenticated user** rather than as the application

For most integrations, server-to-server authentication is sufficient and simpler to implement.

## Quick Start

### 1. Configure OAuth in Adobe Developer Console

First, create an OAuth Web App credential in the [Adobe Developer Console](https://developer.adobe.com/):

1. Create or select a project
2. Add the "Frame.io API" service
3. Create an "OAuth Web App" credential
4. Note your Client ID and Client Secret
5. Add your callback URL (e.g., `https://yourapp.com/auth/callback`)

### 2. Configure Your App

Initialize your app with OAuth configuration:

```python
import os

from frameio_kit import App, OAuthConfig
from key_value.aio.stores.disk import DiskStore

app = App(
    oauth=OAuthConfig(
        client_id=os.environ["ADOBE_CLIENT_ID"],
        client_secret=os.environ["ADOBE_CLIENT_SECRET"],
        base_url="https://yourapp.com",
        storage=DiskStore(directory="./tokens"),  # Persist tokens to disk
    )
)
```

### 3. Require User Auth for Actions

Add `require_user_auth=True` to actions that need user authentication:

```python
from frameio_kit import ActionEvent, Client, Message, get_user_token

@app.on_action(
    event_type="myapp.process_file",
    name="Process File",
    description="Process file with user credentials",
    secret=os.environ["ACTION_SECRET"],
    require_user_auth=True,  # Enable user authentication
)
async def process_file(event: ActionEvent):
    # Get the user's token (not exposed on event to prevent accidental logging)
    token = get_user_token()

    # Create a client with the user's token
    user_client = Client(token=token)

    # Fetch the authenticated user's profile
    profile = await user_client.users.show()

    # Make API calls as the authenticated user
    file = await user_client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )

    return Message(
        title="File Processed",
        description=f"Processed {file.data.name} as {profile.data.name}"
    )
```

## How It Works

1. **User triggers action**: When a user clicks your custom action in Frame.io
2. **Authentication check**: The app checks if the user has a valid token
3. **Login prompt**: If not authenticated, the user sees a "Sign in with Adobe" button
4. **OAuth flow**: User is redirected to Adobe Login, authorizes your app
5. **Token storage**: Access and refresh tokens are encrypted and stored
6. **Handler execution**: Your handler can call `get_user_token()` to retrieve the token
7. **Automatic refresh**: Tokens are automatically refreshed when expired

## OAuth Configuration

The `OAuthConfig` class accepts the following parameters:

### Required Parameters

- **`client_id`**: Adobe IMS application client ID from Adobe Developer Console
- **`client_secret`**: Adobe IMS application client secret
- **`base_url`**: Base URL of your application (e.g., "https://myapp.com"). The OAuth callback will be automatically constructed as `{base_url}/auth/callback` and must be registered in Adobe Console.

### Optional Parameters

- **`scopes`**: List of OAuth scopes (default: `["additional_info.roles", "offline_access", "profile", "email", "openid"]`)
- **`storage`**: Storage backend for tokens (default: `MemoryStore()`)
- **`encryption_key`**: Explicit encryption key (default: uses environment variable or generates ephemeral key)

### Example with All Options

```python
from key_value.aio.stores.redis import RedisStore

app = App(
    oauth=OAuthConfig(
        client_id=os.environ["ADOBE_CLIENT_ID"],
        client_secret=os.environ["ADOBE_CLIENT_SECRET"],
        base_url="https://yourapp.com/auth/callback",
        scopes=["openid", "AdobeID", "frameio.api"],
        storage=RedisStore(url="redis://localhost:6379"),
        encryption_key=os.environ["FRAMEIO_AUTH_ENCRYPTION_KEY"],
    )
)
```

## Storage Backends

Tokens are encrypted at rest using Fernet symmetric encryption. Choose a storage backend based on your deployment:

### Development: MemoryStore (Default)

Tokens are stored in memory and lost on restart:

```python
# No storage parameter needed - MemoryStore is the default
app = App(oauth=OAuthConfig(...))
```

### Single Server: DiskStore

Tokens persist to disk:

```python
from key_value.aio.stores.disk import DiskStore

app = App(
    oauth=OAuthConfig(
        ...,
        storage=DiskStore(directory="./tokens"),
    )
)
```

### Multi-Server: RedisStore

Tokens shared across servers via Redis:

```python
from key_value.aio.stores.redis import RedisStore

app = App(
    oauth=OAuthConfig(
        ...,
        storage=RedisStore(url="redis://localhost:6379"),
    )
)
```

### Multi-Server: DynamoDB

Tokens shared across servers via AWS DynamoDB:

```python
from key_value.aio.stores.dynamodb import DynamoDBStore

app = App(
    oauth=OAuthConfig(
        ...,
        storage=DynamoDBStore(
            table_name="frameio-oauth-tokens",
            region_name="us-east-1",
        ),
    )
)
```

**Note**: DynamoDB table must have:
- **Partition key**: `key` (String)
- **TTL attribute**: `ttl` (Number) - Enable TTL on this attribute for automatic cleanup

All storage backends use the [py-key-value-aio](https://github.com/strawgate/py-key-value) library.

## Encryption Key Management

Tokens are encrypted using Fernet symmetric encryption. The encryption key is loaded in the following priority:

1. **Explicit key** in `OAuthConfig(encryption_key="...")`
2. **Environment variable** `FRAMEIO_AUTH_ENCRYPTION_KEY`
3. **Ephemeral key** (generated on startup, lost on restart)

### Production Deployment

For production, set an explicit encryption key via environment variable:

```bash
# Generate a key (run once)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set environment variable
export FRAMEIO_AUTH_ENCRYPTION_KEY="your-generated-key"
```

Store this key securely (e.g., AWS Secrets Manager, HashiCorp Vault).

## OAuth Endpoints

When OAuth is configured, the following endpoints are automatically mounted:

- **`GET /auth/login`**: Initiates OAuth flow
  - Query params: `user_id` (required), `interaction_id` (optional)
- **`GET /auth/callback`**: Handles OAuth callback from Adobe

You don't need to implement these routes - they're handled automatically.

## Token Lifecycle

### Automatic Refresh

Tokens are automatically refreshed when they expire:

- Access tokens typically last 24 hours
- Refresh happens automatically with a 5-minute buffer
- Failed refresh deletes the token (user must re-authenticate)

### Token Deletion

To log out a user or revoke access:

```python
# Delete user's token
await app.token_manager.delete_token(user_id="user_123")
```

## Security Considerations

### CSRF Protection

OAuth state tokens protect against CSRF attacks:

- Random state tokens with 10-minute expiration
- State verified on callback
- Expired states automatically cleaned up

### Token Encryption

All stored tokens are encrypted using Fernet:

- AES 128-bit encryption in CBC mode
- HMAC signature for integrity
- Random IV for each encryption

### HTTPS Required

OAuth callback URLs **must** use HTTPS in production. Adobe will reject HTTP callbacks.

## Multi-Server Deployments

For apps running on multiple servers:

1. Use **RedisStore** or similar distributed storage
2. Ensure all servers use the **same encryption key**
3. OAuth state uses the same storage backend (automatically distributed)

## Error Handling

### User Not Authenticated

When `require_user_auth=True` and user isn't authenticated, they see a login form automatically. No code needed.

### Token Refresh Failed

If token refresh fails (e.g., user revoked access), the token is deleted and user must re-authenticate on next action.

### OAuth Configuration Errors

```python
# Raises RuntimeError if OAuth not configured but auth required
@app.on_action(..., require_user_auth=True)
async def handler(event):
    pass  # Error if app initialized without oauth parameter
```

## Mixing S2S and User Auth

You can use both authentication methods in the same app:

```python
app = App(
    token=os.getenv("FRAMEIO_S2S_TOKEN"),  # Server-to-server
    oauth=OAuthConfig(...),  # User authentication
)

# S2S authentication (default)
@app.on_action(...)
async def admin_action(event: ActionEvent):
    # Uses app.client with S2S token
    await app.client.files.show(...)

# User authentication
@app.on_action(..., require_user_auth=True)
async def user_action(event: ActionEvent):
    # Get user's token from context
    user_client = Client(token=get_user_token())
    await user_client.files.show(...)
```

## Testing

For testing, use MemoryStore and mock token data:

```python
import pytest
from frameio_kit import App, OAuthConfig
from key_value.aio.stores.memory import MemoryStore

@pytest.fixture
def app():
    return App(
        oauth=OAuthConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            base_url="http://localhost:8000/auth/callback",
            storage=MemoryStore(),
        )
    )
```

## Troubleshooting

### "Invalid signature" errors

Ensure your callback URL in Adobe Console matches exactly (including trailing slash).

### Tokens not persisting

Check that your storage backend is configured correctly. DiskStore directory must be writable.

### Users repeatedly asked to login

- Check encryption key consistency across restarts
- Verify storage backend is persisting data
- Ensure token refresh is working (check logs)

### "redirect_uri_mismatch" error

Your `redirect_uri` in OAuthConfig must exactly match one registered in Adobe Developer Console.

## Next Steps

- Review the [Custom Actions guide](custom_actions.md) for action best practices
- Check the [API Reference](../api_reference.md) for detailed OAuth types
- See the [Middleware guide](middleware.md) for request interception
