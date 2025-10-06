# OAuth User Authorization Guide

This guide explains how to implement OAuth user authorization in your Frame.io app using frameio-kit.

## Overview

OAuth authorization is necessary when your custom action needs to perform API operations on behalf of a specific user. This is common for actions that:

- Create or modify assets with user-specific permissions
- Access user-specific data or settings
- Need to respect user-level access controls

## Architecture

The OAuth flow in frameio-kit consists of several components:

1. **OAuthManager**: Handles OAuth URL generation, token exchange, and token refresh
2. **TokenStore**: Your implementation for persisting user tokens
3. **OAuth Callback Route**: Automatically handles the redirect from Frame.io
4. **User Client**: API client authenticated with user tokens

## Implementation Steps

### 1. Choose a TokenStore Implementation

frameio-kit provides built-in token storage implementations. You can use these directly or implement your own:

#### Option 1: In-Memory Storage (Development)

```python
from frameio_kit import App, InMemoryTokenStore

app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri="https://yourapp.com/oauth/callback",
    token_store=InMemoryTokenStore()
)
```

**Warning**: Tokens are lost on restart. Only use for development.

#### Option 2: DynamoDB Storage (Production)

```python
from frameio_kit import App, DynamoDBTokenStore

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

#### Option 3: Custom Storage

```python
from frameio_kit import TokenStore

class CustomTokenStore(TokenStore):
    async def save_token(self, user_id: str, token_data: dict):
        # Implement your storage logic
        pass
    
    async def get_token(self, user_id: str) -> dict | None:
        # Implement your retrieval logic
        pass
```

### 2. Initialize App with OAuth Credentials

Configure your app with OAuth credentials from the Frame.io Developer Console:

```python
from frameio_kit import App

app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri="https://yourapp.com/oauth/callback",
    token_store=MongoTokenStore(os.getenv("MONGODB_URI"))
)
```

**Important**: The `oauth_redirect_uri` must be registered in your Frame.io app settings.

### 3. Implement the Custom Action Handler

Your action handler should check for user authorization and handle both scenarios:

```python
from frameio_kit import ActionEvent, Message

@app.on_action(
    event_type="my_action",
    name="My Action",
    description="Performs action on behalf of user",
    secret=os.getenv("ACTION_SECRET")
)
async def my_action(event: ActionEvent):
    # Check if user has authorized
    user_token = await app.oauth.get_user_token(event.user.id)
    
    if not user_token:
        # Show authorization message with URL
        auth_url = app.oauth.get_authorization_url(
            state=f"{event.user.id}:{event.interaction_id}"
        )
        return Message(
            title="Authorization Required",
            description=f"Please visit this URL to authorize: {auth_url}\n\n"
                       f"After authorizing, trigger this action again."
        )
    
    # User is authorized - proceed with action
    user_client = await app.get_user_client(event.user.id)
    
    # Make API calls on behalf of the user
    asset = await user_client.assets.get(
        account_id=event.account_id,
        asset_id=event.resource_id
    )
    
    # ... perform your action ...
    
    return Message(
        title="Success",
        description="Action completed successfully"
    )
```

## OAuth Flow Sequence

Here's what happens during the OAuth flow:

```
1. User triggers custom action
   └─> Your handler checks for token
       └─> No token found
           └─> Return Message with authorization URL

2. User visits authorization URL
   └─> Redirected to Frame.io OAuth page
       └─> User approves authorization
           └─> Frame.io redirects to your callback URL

3. OAuth callback handler (/oauth/callback)
   └─> Receives authorization code
       └─> Exchanges code for tokens
           └─> Saves tokens to TokenStore
               └─> Returns success message

4. User triggers action again
   └─> Your handler checks for token
       └─> Token found!
           └─> Creates user-specific client
               └─> Performs action with user permissions
```

## State Parameter

The `state` parameter is crucial for security and correlation:

```python
auth_url = app.oauth.get_authorization_url(
    state=f"{event.user.id}:{event.interaction_id}"
)
```

**Format**: `"user_id:interaction_id"`

- **user_id**: Used to associate the token with the correct user
- **interaction_id**: Can help correlate the authorization with the original action

The callback handler automatically parses this and saves the token for the user.

## Token Refresh

OAuth access tokens expire after a certain time. The `OAuthManager` provides a `refresh_token` method:

```python
# Manually refresh a token
new_token_data = await app.oauth.refresh_token(old_refresh_token)
```

For automatic refresh, you should implement expiration checking in your `TokenStore`:

```python
class SmartTokenStore(TokenStore):
    async def get_token(self, user_id: str) -> dict | None:
        token_data = await self._retrieve_from_db(user_id)
        
        if not token_data:
            return None
        
        # Check if token is expired
        if self._is_expired(token_data):
            # Refresh the token
            oauth_manager = self._get_oauth_manager()
            new_token_data = await oauth_manager.refresh_token(
                token_data["refresh_token"]
            )
            # Save new token
            await self.save_token(user_id, new_token_data.model_dump())
            return new_token_data.model_dump()
        
        return token_data
    
    def _is_expired(self, token_data: dict) -> bool:
        # Check if token is expired based on stored timestamp
        expires_at = token_data.get("expires_at")
        return datetime.utcnow() >= expires_at
```

## Security Considerations

1. **Store tokens securely**: Use encryption at rest for token storage
2. **Use HTTPS**: Always use HTTPS for your callback URL
3. **Validate state parameter**: Prevents CSRF attacks
4. **Limit token scope**: Request only the OAuth scopes you need
5. **Handle token expiration**: Implement proper refresh logic

## Error Handling

Handle common error scenarios:

```python
@app.on_action(...)
async def my_action(event: ActionEvent):
    try:
        user_token = await app.oauth.get_user_token(event.user.id)
        
        if not user_token:
            return _show_auth_form(event)
        
        user_client = await app.get_user_client(event.user.id)
        
        # Perform action
        result = await user_client.assets.get(...)
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Token is invalid/expired - prompt for re-authorization
            return _show_auth_form(event)
        else:
            # Other API error
            return Message(
                title="Error",
                description=f"API error: {e.response.status_code}"
            )
    
    except Exception as e:
        # Unexpected error
        return Message(
            title="Error",
            description="An unexpected error occurred"
        )
```

## Testing OAuth Locally

When developing locally, you need a way to receive the OAuth callback. Options include:

1. **ngrok**: Create a public URL for your local server
   ```bash
   ngrok http 8000
   # Use the ngrok URL as your redirect_uri
   ```

2. **localhost.run**: Similar to ngrok
   ```bash
   ssh -R 80:localhost:8000 localhost.run
   ```

3. **Production-like environment**: Deploy to a staging server with HTTPS

## Complete Example

See `examples/oauth_custom_action.py` for a complete working example.

## Troubleshooting

### "OAuth not configured" error
- Ensure all three OAuth parameters are provided to `App()`
- Check environment variables are set correctly

### Callback doesn't work
- Verify redirect_uri matches exactly in Frame.io Developer Console
- Check your server is accessible at the callback URL
- Ensure the route is `/oauth/callback`

### Token not saved
- Check your `TokenStore.save_token()` implementation
- Verify database connection
- Look for errors in server logs

### "No token found for user" error
- User hasn't completed authorization flow
- Token was not saved properly
- Check token_store implementation

## API Reference

### OAuthManager

- `get_authorization_url(state, scope)`: Generate OAuth URL
- `exchange_code_for_token(code)`: Exchange code for tokens
- `refresh_token(refresh_token)`: Refresh expired token
- `get_user_token(user_id)`: Get valid token for user

### TokenStore (Abstract)

- `save_token(user_id, token_data)`: Save token to storage
- `get_token(user_id)`: Retrieve token from storage

### App OAuth Methods

- `app.oauth`: Access OAuthManager instance
- `app.get_user_client(user_id)`: Create user-specific API client
