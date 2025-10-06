# OAuth Implementation for Frame.io Kit

This document describes the OAuth user authorization implementation for frameio-kit, allowing custom actions to perform operations on behalf of users.

## Overview

The OAuth implementation enables custom actions to:
- Obtain user tokens through OAuth 2.0 flow
- Store and retrieve user tokens securely
- Make API calls on behalf of users
- Handle token refresh and expiration

## Architecture

### Core Components

1. **OAuthManager** (`src/frameio_kit/oauth.py`)
   - Generates OAuth authorization URLs
   - Exchanges authorization codes for tokens
   - Refreshes expired tokens
   - Retrieves stored user tokens

2. **TokenStore Interface** (`src/frameio_kit/oauth.py`)
   - Abstract base class for token storage
   - Methods: `save_token()`, `get_token()`
   - Developers implement this for their storage backend

3. **Built-in TokenStore Implementations** (`src/frameio_kit/token_stores.py`)
   - `InMemoryTokenStore`: Development/testing only (tokens lost on restart)
   - `DynamoDBTokenStore`: Production-ready persistent storage with AWS DynamoDB

4. **App Integration** (`src/frameio_kit/app.py`)
   - OAuth configuration in App constructor
   - `app.oauth` property for accessing OAuthManager
   - `app.get_user_client(user_id)` method for creating user-specific clients
   - `/oauth/callback` route automatically handles OAuth callbacks

## User Experience Flow

### 1. Initial Action Trigger (No Authorization)

User triggers custom action → Handler detects no token → Returns Message with authorization URL

```python
if not user_token:
    auth_url = app.oauth.get_authorization_url(
        state=f"{event.user.id}:{event.interaction_id}"
    )
    return Message(
        title="Authorization Required",
        description=f"Please visit this URL to authorize: {auth_url}\n\n"
                   f"After authorizing, trigger this action again."
    )
```

### 2. User Authorization

User visits URL → Frame.io OAuth page → User approves → Redirect to `/oauth/callback` → Tokens stored

### 3. Subsequent Action Triggers (Authorized)

User triggers action again → Handler detects token → Creates user client → Performs action

```python
user_client = await app.get_user_client(event.user.id)
asset = await user_client.assets.get(...)
# Perform user-specific operations
```

## Storage Implementations

### InMemoryTokenStore

**Use Case**: Development and testing only

**Characteristics**:
- Simple dictionary-based storage
- All tokens lost on app restart
- No external dependencies
- Zero configuration

**Usage**:
```python
from frameio_kit import App, InMemoryTokenStore

app = App(
    oauth_client_id="...",
    oauth_client_secret="...",
    oauth_redirect_uri="...",
    token_store=InMemoryTokenStore()
)
```

### DynamoDBTokenStore

**Use Case**: Production deployments

**Characteristics**:
- Persistent storage in AWS DynamoDB
- Automatic TTL-based cleanup (optional)
- Scalable and highly available
- Stores expiration timestamps
- Requires boto3 dependency

**Table Schema**:
- Partition Key: `user_id` (String)
- Attributes:
  - `access_token`: OAuth access token
  - `refresh_token`: OAuth refresh token
  - `expires_in`: Token duration in seconds
  - `expires_at`: ISO timestamp of expiration
  - `token_type`: Usually "Bearer"
  - `ttl`: Unix timestamp for DynamoDB TTL
  - `updated_at`: ISO timestamp of last update

**Setup**:
```bash
aws dynamodb create-table \
    --table-name frameio-user-tokens \
    --attribute-definitions AttributeName=user_id,AttributeType=S \
    --key-schema AttributeName=user_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

aws dynamodb update-time-to-live \
    --table-name frameio-user-tokens \
    --time-to-live-specification "Enabled=true, AttributeName=ttl"
```

**Usage**:
```python
from frameio_kit import App, DynamoDBTokenStore

token_store = DynamoDBTokenStore(
    table_name="frameio-user-tokens",
    region_name="us-east-1",
    enable_ttl=True,
    ttl_days=90
)

app = App(
    oauth_client_id="...",
    oauth_client_secret="...",
    oauth_redirect_uri="...",
    token_store=token_store
)
```

## Security Considerations

1. **State Parameter**: Always include user_id in state for CSRF protection
2. **HTTPS Required**: OAuth redirect_uri must use HTTPS in production
3. **Token Storage**: Encrypt tokens at rest in your storage backend
4. **Token Scope**: Request minimal OAuth scopes needed
5. **Expiration Handling**: Implement token refresh logic
6. **Secure Secrets**: Never commit OAuth credentials to version control

## Configuration

### Environment Variables

Required for all OAuth implementations:
- `OAUTH_CLIENT_ID`: From Frame.io Developer Console
- `OAUTH_CLIENT_SECRET`: From Frame.io Developer Console  
- `OAUTH_REDIRECT_URI`: Your callback URL (must be registered in Frame.io)

Additional for DynamoDB:
- `AWS_REGION`: AWS region (default: us-east-1)
- `DYNAMODB_TABLE_NAME`: Table name (default: frameio-user-tokens)
- `AWS_ACCESS_KEY_ID`: AWS credentials (or use IAM role)
- `AWS_SECRET_ACCESS_KEY`: AWS credentials (or use IAM role)

### App Initialization

```python
from frameio_kit import App, DynamoDBTokenStore

app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),           # App-level token
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri=os.getenv("OAUTH_REDIRECT_URI"),
    token_store=DynamoDBTokenStore(
        table_name=os.getenv("DYNAMODB_TABLE_NAME", "frameio-user-tokens"),
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )
)
```

## API Reference

### OAuthManager

```python
# Generate authorization URL
auth_url = app.oauth.get_authorization_url(
    state="user_123:interaction_456",
    scope="asset.create"
)

# Exchange code for tokens (handled automatically by callback)
token_data = await app.oauth.exchange_code_for_token(code)

# Refresh expired token
new_token_data = await app.oauth.refresh_token(refresh_token)

# Get user token (with auto-refresh if implemented)
access_token = await app.oauth.get_user_token(user_id)
```

### App OAuth Methods

```python
# Access OAuth manager
app.oauth  # Raises RuntimeError if OAuth not configured

# Create user-specific client
user_client = await app.get_user_client(user_id)
# Raises RuntimeError if no token found

# Use user client for API calls
asset = await user_client.assets.get(account_id, asset_id)
```

### TokenStore Interface

```python
class CustomTokenStore(TokenStore):
    async def save_token(self, user_id: str, token_data: dict[str, Any]) -> None:
        """Save token data for a user."""
        pass
    
    async def get_token(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve token data for a user."""
        pass
```

## Examples

### Basic OAuth Action

See `examples/oauth_custom_action.py` for a complete example using InMemoryTokenStore.

### Production OAuth Action

See `examples/oauth_dynamodb_example.py` for a production-ready example using DynamoDB.

### Complete Guide

See `examples/oauth_guide.md` for comprehensive documentation and best practices.

## Testing

### Unit Tests

OAuth functionality is tested in `tests/test_oauth.py`:
- Authorization URL generation
- Token exchange
- Token refresh
- Callback handling
- Storage operations
- Error handling

### Manual Testing with ngrok

For local development:
```bash
# Start ngrok
ngrok http 8000

# Use the ngrok URL as your redirect_uri
export OAUTH_REDIRECT_URI="https://abc123.ngrok.io/oauth/callback"

# Run your app
python examples/oauth_custom_action.py
```

## Migration Path

### From No OAuth to OAuth

1. Add OAuth credentials to your App initialization
2. Implement or use a TokenStore
3. Update action handlers to check for user tokens
4. Handle authorization flow in your handlers
5. Test with development token store
6. Deploy with production token store (DynamoDB)

### Custom Storage Migration

If you have existing token storage:
```python
class ExistingTokenStore(TokenStore):
    def __init__(self, existing_db):
        self.db = existing_db
    
    async def save_token(self, user_id: str, token_data: dict):
        # Adapt to your existing schema
        await self.db.store_oauth_token(user_id, token_data)
    
    async def get_token(self, user_id: str) -> dict | None:
        # Adapt from your existing schema
        return await self.db.retrieve_oauth_token(user_id)
```

## Troubleshooting

### "OAuth not configured" error
- Ensure all three OAuth parameters are provided to App()
- Check environment variables are set

### Callback doesn't work
- Verify redirect_uri matches Frame.io Developer Console exactly
- Ensure route is `/oauth/callback`
- Check server is accessible at callback URL
- Verify HTTPS is used in production

### "No token found for user" error
- User hasn't completed authorization flow
- Token wasn't saved (check TokenStore implementation)
- Token was deleted or expired

### DynamoDB errors
- Check AWS credentials are configured
- Verify table exists and has correct schema
- Ensure IAM permissions for DynamoDB operations
- Check region matches table location

## Future Enhancements

Potential improvements for future versions:
- Automatic token refresh with expiration tracking
- Redis TokenStore implementation
- PostgreSQL TokenStore implementation
- Token revocation support
- Multi-scope OAuth support
- Token encryption at rest in built-in stores
- OAuth state validation middleware
- Rate limiting for token operations

## Resources

- Frame.io OAuth Documentation: [Frame.io Developer Portal]
- AWS DynamoDB Documentation: https://docs.aws.amazon.com/dynamodb/
- OAuth 2.0 Specification: https://oauth.net/2/
