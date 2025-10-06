# OAuth Quick Start Guide

The easiest way to add user authorization to your Frame.io custom actions.

## The Simple Way

With frameio-kit, adding OAuth is as simple as returning `RequireAuth()`:

```python
from frameio_kit import App, ActionEvent, RequireAuth, InMemoryTokenStore

app = App(
    oauth_client_id="your_client_id",
    oauth_client_secret="your_client_secret", 
    oauth_redirect_uri="https://yourapp.com/oauth/callback",
    token_store=InMemoryTokenStore()  # Use DynamoDBTokenStore for production
)

@app.on_action(
    event_type="export.asset",
    name="Export Asset",
    description="Export this asset",
    secret="your_secret"
)
async def export_asset(event: ActionEvent):
    # Check if user has authorized
    user_token = await app.oauth.get_user_token(event.user.id)
    
    if not user_token:
        # That's it! Framework handles the rest
        return RequireAuth()
    
    # User is authorized - do your thing
    user_client = await app.get_user_client(event.user.id)
    asset = await user_client.assets.get(
        account_id=event.account_id,
        asset_id=event.resource_id
    )
    
    # ... perform your action ...
    
    return Message(title="Done!", description=f"Exported {asset.name}")
```

## What Happens

1. **User triggers action** → No token found → Return `RequireAuth()`
2. **Framework automatically**:
   - Generates OAuth authorization URL
   - Creates a message with the URL
   - Shows it to the user
3. **User visits URL** → Approves → Redirected to your callback
4. **Framework automatically**:
   - Exchanges code for tokens
   - Stores tokens in your TokenStore
5. **User triggers action again** → Token found → Action executes!

## Customizing the Message

```python
return RequireAuth(
    title="Connect Your Account",
    description="To export files, we need access to your Frame.io account."
)
```

The framework automatically appends the authorization URL and instructions.

## Before vs After

### ❌ Without RequireAuth (the old way)

```python
if not user_token:
    # You had to manually:
    auth_url = app.oauth.get_authorization_url(
        state=f"{event.user.id}:{event.interaction_id}"  # Remember to include state!
    )
    return Message(
        title="Authorization Required",
        description=f"Please visit this URL: {auth_url}\n\n"
                   f"After authorizing, trigger this action again."
    )
```

### ✅ With RequireAuth (the new way)

```python
if not user_token:
    return RequireAuth()  # Done!
```

## Production Setup

For production, use DynamoDB token storage:

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

Create the DynamoDB table:
```bash
aws dynamodb create-table \
    --table-name frameio-user-tokens \
    --attribute-definitions AttributeName=user_id,AttributeType=S \
    --key-schema AttributeName=user_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST
```

## Complete Example

See `examples/oauth_custom_action.py` for a complete working example.

## That's It!

No manual URL generation, no state parameter handling, no message construction. Just return `RequireAuth()` and the framework does the rest.

For more details, see the [complete OAuth guide](examples/oauth_guide.md).
