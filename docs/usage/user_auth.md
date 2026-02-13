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
5. Add your callback URL: `https://yourapp.com/auth/callback`

### 2. Initialize OAuth

```python
import os
from frameio_kit import App, OAuthConfig

app = App(
    oauth=OAuthConfig(
        client_id=os.environ["ADOBE_CLIENT_ID"],
        client_secret=os.environ["ADOBE_CLIENT_SECRET"],
    )
)
```

!!! note "Automatic Redirect URL Inference"

    By default, the OAuth callback URL is automatically inferred from incoming requests. This inference relies on proper forwarding of headers (`X-Forwarded-Host`, `X-Forwarded-Proto`) from reverse proxies or load balancers. For such deployments, you may need to set `redirect_url` explicitly. See [Redirect URL Configuration](#redirect-url-configuration).

!!! note "Token Storage"

    By default, tokens are stored in memory and lost on restart. For multi-server deployments or persistence, see [Storage Backends](#storage-backends).

### 3. Require Auth in Actions

```python
from frameio_kit import ActionEvent, Client, Message, get_user_token

@app.on_action(
    event_type="myapp.process_file",
    name="Process File",
    description="Process file with user credentials",
    secret=os.environ["ACTION_SECRET"],
    require_user_auth=True,
)
async def process_file(event: ActionEvent):
    # Get the user's token from context
    token = get_user_token()

    # Create client with user's token
    async with Client(token=token) as user_client:
        # Fetch the authenticated user's profile
        profile = await user_client.users.show()

        # Make API calls as the user
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

1. User clicks your custom action in Frame.io
2. App checks for valid token
3. If not authenticated, user sees "Sign in with Adobe" button
4. User authorizes your app via Adobe Login
5. Tokens are encrypted and stored
6. Handler retrieves token via `get_user_token()`
7. Tokens automatically refresh when expired

## Configuration

### Required Parameters

- `client_id` - Adobe IMS client ID
- `client_secret` - Adobe IMS client secret

### Optional Parameters

- `redirect_url` - Full OAuth callback URL (default: automatically inferred). Set explicitly for reverse proxy scenarios.
- `scopes` - OAuth scopes (default: `["additional_info.roles", "offline_access", "profile", "email", "openid"]`)
- `storage` - Token storage backend (default: `MemoryStorage()`)
- `encryption_key` - Explicit encryption key (default: environment variable or ephemeral)

### Redirect URL Configuration

Set `redirect_url` explicitly when:

- Behind a reverse proxy without proper forwarded headers
- Public URL differs from what the application sees
- Load balancer doesn't forward `X-Forwarded-Host` and `X-Forwarded-Proto` headers

```python
app = App(
    oauth=OAuthConfig(
        client_id=os.environ["ADOBE_CLIENT_ID"],
        client_secret=os.environ["ADOBE_CLIENT_SECRET"],
        redirect_url="https://yourapp.com/auth/callback",
    )
)
```

Make sure to consider [mounting](mounting.md) when setting the `redirect_url`.

!!! warning "Important: Mount Path Consideration"
    If you mount your app at a subpath (e.g., `/frameio`), your `redirect_url` must include the mount path.
    For example, if your app is mounted at `/frameio`, set:
    `redirect_url="https://yourapp.com/frameio/auth/callback"`
    not
    `redirect_url="https://yourapp.com/auth/callback"`
### Complete Example

```python
from frameio_kit import DynamoDBStorage

app = App(
    oauth=OAuthConfig(
        client_id=os.environ["ADOBE_CLIENT_ID"],
        client_secret=os.environ["ADOBE_CLIENT_SECRET"],
        redirect_url="https://yourapp.com/auth/callback",  # Explicit for proxy
        scopes=["openid", "AdobeID", "frameio.api"],
        storage=DynamoDBStorage(table_name="frameio-app-data"),
        encryption_key=os.environ["FRAMEIO_AUTH_ENCRYPTION_KEY"],
    )
)
```

## Storage Backends

Tokens are encrypted at rest. Choose a backend based on your deployment:

### Development: MemoryStorage

Tokens stored in memory (lost on restart):

```python
# Default - no storage parameter needed
app = App(oauth=OAuthConfig(...))
```

### Multi-Server: DynamoDBStorage

Install the optional dependency:

```bash
pip install frameio-kit[dynamodb]
```

Tokens shared via AWS DynamoDB:

```python
from frameio_kit import DynamoDBStorage

app = App(
    oauth=OAuthConfig(
        ...,
        storage=DynamoDBStorage(table_name="frameio-app-data"),
    )
)
```

The DynamoDB table requires a partition key `PK` (String) and TTL enabled on the `ttl` attribute.

```hcl
resource "aws_dynamodb_table" "frameio_app_data" {
  name         = "frameio-app-data"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"

  attribute {
    name = "PK"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
```

### Custom Storage

Implement the `Storage` protocol for any other backend:

```python
from frameio_kit import Storage

class RedisStorage:
    async def get(self, key: str) -> dict | None:
        ...

    async def put(self, key: str, value: dict, *, ttl: int | None = None) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...

app = App(
    oauth=OAuthConfig(
        ...,
        storage=RedisStorage(),
    )
)
```

## Encryption

Tokens are encrypted using Fernet symmetric encryption. The key is loaded in priority order:

1. Explicit `encryption_key` in OAuthConfig
2. Environment variable `FRAMEIO_AUTH_ENCRYPTION_KEY`
3. Ephemeral key (generated on startup, lost on restart)

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
    async with Client(token=get_user_token()) as user_client:
        await user_client.files.show(...)
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

- The inferred or configured `redirect_url` must match one registered in Adobe Developer Console
- If using automatic inference, register the callback URL you expect (e.g., `https://yourapp.com/auth/callback`)
- If behind a proxy, either configure forwarded headers or set `redirect_url` explicitly

## Next Steps

- [Custom Actions](custom_actions.md) - Learn about building interactive workflows
- [Client API](client_api.md) - Understand API authentication patterns
- [API Reference](../api_reference.md) - Detailed OAuth types documentation
