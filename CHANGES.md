# OAuth Implementation Changes

This document summarizes the OAuth user authorization implementation added to frameio-kit.

## What Was Added

### Core OAuth Module (`src/frameio_kit/oauth.py`)

- **`RequireAuth`** class: Simple return value for handlers requiring user auth
  - Framework automatically generates auth URL and message
  - Optional custom title and description
  - Example: `return RequireAuth()` or `return RequireAuth(title="Connect Account")`

- **`OAuthManager`** class: Handles OAuth 2.0 flows
  - `get_authorization_url()`: Generate OAuth authorization URLs
  - `exchange_code_for_token()`: Exchange auth code for tokens
  - `refresh_token()`: Refresh expired tokens
  - `get_user_token()`: Retrieve stored user tokens

- **`TokenStore`** interface: Abstract base for token storage
  - `save_token()`: Persist user tokens
  - `get_token()`: Retrieve user tokens

- **`TokenData`** model: Pydantic model for token validation

### Token Storage Implementations (`src/frameio_kit/token_stores.py`)

- **`InMemoryTokenStore`**: Development/testing storage
  - Simple dictionary-based
  - Tokens lost on restart
  - Zero configuration

- **`DynamoDBTokenStore`**: Production storage
  - AWS DynamoDB backed
  - Persistent and scalable
  - Automatic TTL cleanup
  - Requires boto3

### App Integration (`src/frameio_kit/app.py`)

- **OAuth configuration** in App constructor:
  - `oauth_client_id`: OAuth client ID
  - `oauth_client_secret`: OAuth client secret
  - `oauth_redirect_uri`: OAuth callback URL
  - `token_store`: TokenStore implementation

- **`app.oauth`** property: Access OAuthManager

- **`app.get_user_client(user_id)`**: Create user-specific API client

- **`/oauth/callback`** route: Automatic OAuth callback handling
  - Exchanges code for tokens
  - Saves tokens to TokenStore
  - Returns success message

- **RequireAuth handling**: Framework automatically detects `RequireAuth` return value
  - Generates authorization URL with proper state
  - Constructs Message with URL
  - Returns to user

### Updated Type Hints

- `ActionHandlerFunc` now includes `RequireAuth` as valid return type

## Developer Experience

### Before (Manual approach)

```python
@app.on_action(...)
async def my_action(event: ActionEvent):
    user_token = await app.oauth.get_user_token(event.user.id)
    
    if not user_token:
        # Manual URL generation
        auth_url = app.oauth.get_authorization_url(
            state=f"{event.user.id}:{event.interaction_id}"
        )
        # Manual message construction
        return Message(
            title="Authorization Required",
            description=f"Visit: {auth_url}\nThen try again."
        )
    
    # ... proceed with action
```

### After (with RequireAuth)

```python
@app.on_action(...)
async def my_action(event: ActionEvent):
    user_token = await app.oauth.get_user_token(event.user.id)
    
    if not user_token:
        return RequireAuth()  # Done!
    
    # ... proceed with action
```

## Example Code

### Basic Example

```python
from frameio_kit import App, ActionEvent, RequireAuth, InMemoryTokenStore, Message

app = App(
    oauth_client_id="client_id",
    oauth_client_secret="client_secret",
    oauth_redirect_uri="https://app.com/oauth/callback",
    token_store=InMemoryTokenStore()
)

@app.on_action(
    event_type="export.asset",
    name="Export Asset",
    description="Export this asset",
    secret="secret"
)
async def export_asset(event: ActionEvent):
    user_token = await app.oauth.get_user_token(event.user.id)
    
    if not user_token:
        return RequireAuth()
    
    user_client = await app.get_user_client(event.user.id)
    asset = await user_client.assets.get(
        account_id=event.account_id,
        asset_id=event.resource_id
    )
    
    return Message(title="Done", description=f"Exported {asset.name}")
```

### Production Example with DynamoDB

```python
from frameio_kit import App, DynamoDBTokenStore

app = App(
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri=os.getenv("OAUTH_REDIRECT_URI"),
    token_store=DynamoDBTokenStore(
        table_name="frameio-user-tokens",
        region_name="us-east-1"
    )
)
```

## Documentation

### New Files

- **`OAUTH_QUICKSTART.md`**: Quick start guide for OAuth
- **`OAUTH_IMPLEMENTATION.md`**: Technical implementation details
- **`examples/oauth_custom_action.py`**: Basic OAuth example
- **`examples/oauth_dynamodb_example.py`**: Production OAuth example
- **`examples/oauth_guide.md`**: Complete OAuth guide

### Updated Files

- **`README.md`**: Added OAuth section with complete examples
- **`src/frameio_kit/__init__.py`**: Export OAuth classes

## Tests

### New Test Files

- **`tests/test_oauth.py`**: OAuth functionality tests
  - Authorization URL generation
  - Token exchange
  - Token refresh
  - Callback handling
  - Storage operations

- **`tests/test_require_auth.py`**: RequireAuth tests
  - Default message generation
  - Custom title/description
  - OAuth not configured error
  - Complete authorization flow

## Key Features

✅ **Simple API**: Just return `RequireAuth()` - framework handles the rest

✅ **Automatic URL Generation**: No manual state parameter handling

✅ **Built-in Storage**: InMemory for dev, DynamoDB for production

✅ **Extensible**: Easy to implement custom TokenStore for any database

✅ **Type Safe**: Full type hints with Pydantic models

✅ **Secure**: Proper state parameter for CSRF protection

✅ **Production Ready**: DynamoDB storage with TTL support

## Migration Path

Existing apps can easily add OAuth:

1. Add OAuth credentials to App initialization
2. Choose a TokenStore (InMemory for dev, DynamoDB for prod)
3. In action handlers, check for user token
4. Return `RequireAuth()` if no token
5. Use `app.get_user_client(user_id)` for user-specific API calls

No breaking changes to existing functionality.

## Files Modified

- `src/frameio_kit/oauth.py` (new)
- `src/frameio_kit/token_stores.py` (new)
- `src/frameio_kit/app.py` (updated)
- `src/frameio_kit/__init__.py` (updated)
- `README.md` (updated)
- `tests/test_oauth.py` (new)
- `tests/test_require_auth.py` (new)
- `examples/oauth_custom_action.py` (new)
- `examples/oauth_dynamodb_example.py` (new)
- `examples/oauth_guide.md` (new)
- `OAUTH_QUICKSTART.md` (new)
- `OAUTH_IMPLEMENTATION.md` (new)
- `CHANGES.md` (new)

## Dependencies

No new required dependencies. Optional dependency:
- `boto3`: Required only for DynamoDBTokenStore

## Summary

The OAuth implementation provides a simple, powerful way for Frame.io apps to act on behalf of users. The `RequireAuth` pattern makes it incredibly easy for developers - just return `RequireAuth()` and the framework handles all the complexity of OAuth authorization.
