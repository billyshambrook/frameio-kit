# User Authentication

Enable Adobe Login OAuth for user-specific authentication. API calls are attributed to individual users in Frame.io's activity logs.

## When to Use

**Use user authentication when you need to:**

- Attribute actions to specific users in activity logs
- Access user-specific resources requiring user permissions
- Perform operations as the authenticated user

**For most integrations, server-to-server authentication is sufficient and simpler.**

## Quick Start

### 1. Configure Adobe OAuth

Create an OAuth credential in the [Adobe Developer Console](https://developer.adobe.com/):

1. Create or select a project
2. Add the "Frame.io API" service
3. Create an "OAuth Web App" credential
4. Note your Client ID and Client Secret
5. Add your callback URL: `https://yourapp.com/.auth/callback`

### 2. Initialize OAuth

```python
from frameio_kit import App, OAuthConfig
from key_value.aio.stores.disk import DiskStore
import os

app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri="https://yourapp.com/.auth/callback",
        storage=DiskStore(directory="./tokens"),
    )
)
```

### 3. Require Auth in Actions

```python
from frameio_kit import ActionEvent, Client, Message

@app.on_action(
    event_type="myapp.process_file",
    name="Process File",
    description="Process file with user credentials",
    secret=os.getenv("ACTION_SECRET"),
    require_user_auth=True,
)
async def process_file(event: ActionEvent):
    # Create client with user's token
    user_client = Client(token=event.user_access_token)

    # Make API calls as the user
    file = await user_client.files.show(
        account_id=event.account_id,
        file_id=event.resource_id
    )

    await user_client.close()
    return Message(text=f"Processed {file.data.name}")
```

## How It Works

1. User clicks your custom action in Frame.io
2. App checks for valid token
3. If not authenticated, user sees "Sign in with Adobe" button
4. User authorizes your app via Adobe Login
5. Tokens are encrypted and stored
6. Handler receives `event.user_access_token`
7. Tokens automatically refresh when expired

## Configuration

### Required Parameters

- `client_id` - Adobe IMS client ID
- `client_secret` - Adobe IMS client secret
- `redirect_uri` - OAuth callback URI (must match Adobe Console)

### Optional Parameters

- `scopes` - OAuth scopes (default: `["openid", "AdobeID", "frameio.api"]`)
- `storage` - Token storage backend (default: `MemoryStore()`)
- `encryption_key` - Explicit encryption key (default: keyring or ephemeral)

### Complete Example

```python
from key_value.aio.stores.redis import RedisStore

app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri="https://yourapp.com/.auth/callback",
        scopes=["openid", "AdobeID", "frameio.api"],
        storage=RedisStore(url="redis://localhost:6379"),
        encryption_key=os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"),
    )
)
```

## Storage Backends

Tokens are encrypted at rest. Choose a backend based on your deployment:

### Development: MemoryStore

Tokens stored in memory (lost on restart):

```python
# Default - no storage parameter needed
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

Tokens shared across servers:

```python
from key_value.aio.stores.redis import RedisStore

app = App(
    oauth=OAuthConfig(
        ...,
        storage=RedisStore(url="redis://localhost:6379"),
    )
)
```

## Encryption

Tokens are encrypted using Fernet symmetric encryption. The key is loaded in priority order:

1. Explicit `encryption_key` in OAuthConfig
2. Environment variable `FRAMEIO_AUTH_ENCRYPTION_KEY`
3. System keyring
4. Ephemeral key (generated on startup, lost on restart)

### Production Setup

Generate and set an encryption key:

```bash
# Generate key (run once)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set environment variable
export FRAMEIO_AUTH_ENCRYPTION_KEY="your-generated-key"
```

Store this key securely (AWS Secrets Manager, HashiCorp Vault, etc.).

## Token Management

### Automatic Refresh

Tokens refresh automatically with a 5-minute buffer. Failed refresh deletes the token (user must re-authenticate).

### Manual Token Deletion

```python
# Log out a user
await app.token_manager.delete_token(user_id="user_123")
```

## Security

**CSRF Protection** - Random state tokens with 10-minute expiration

**Token Encryption** - AES 128-bit encryption with HMAC signature

**HTTPS Required** - OAuth callbacks must use HTTPS in production

**Signature Verification** - Automatically handled by frameio-kit

## Mixing Authentication Methods

Use both S2S and user auth in the same app:

```python
app = App(
    token=os.getenv("FRAMEIO_S2S_TOKEN"),  # Server-to-server
    oauth=OAuthConfig(...),  # User authentication
)

# S2S authentication (default)
@app.on_action(...)
async def admin_action(event: ActionEvent):
    await app.client.files.show(...)

# User authentication
@app.on_action(..., require_user_auth=True)
async def user_action(event: ActionEvent):
    user_client = Client(token=event.user_access_token)
    await user_client.files.show(...)
    await user_client.close()
```

## Troubleshooting

**"Invalid signature" errors**

- Verify callback URL in Adobe Console matches exactly

**Tokens not persisting**

- Check storage backend configuration
- Ensure encryption key consistency across restarts

**Users repeatedly asked to login**

- Verify encryption key is consistent
- Check storage backend is working

**"redirect_uri_mismatch" error**

- `redirect_uri` must exactly match one in Adobe Developer Console

## Next Steps

- [Custom Actions](custom_actions.md) - Learn about building interactive workflows
- [Client API](client_api.md) - Understand API authentication patterns
- [API Reference](../api_reference.md) - Detailed OAuth types documentation
