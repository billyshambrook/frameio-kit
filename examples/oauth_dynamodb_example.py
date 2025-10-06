"""Example: Custom Action with DynamoDB Token Storage

This example demonstrates production-ready OAuth implementation using DynamoDB
for persistent token storage.

Prerequisites:
1. Install boto3: pip install boto3 or uv add boto3
2. Create DynamoDB table (see setup instructions below)
3. Configure AWS credentials (environment variables or IAM role)

Setup:
1. Create the DynamoDB table:
   ```bash
   aws dynamodb create-table \
       --table-name frameio-user-tokens \
       --attribute-definitions AttributeName=user_id,AttributeType=S \
       --key-schema AttributeName=user_id,KeyType=HASH \
       --billing-mode PAY_PER_REQUEST \
       --region us-east-1
   
   # Optional: Enable TTL for automatic cleanup
   aws dynamodb update-time-to-live \
       --table-name frameio-user-tokens \
       --time-to-live-specification "Enabled=true, AttributeName=ttl"
   ```

2. Set environment variables:
   - FRAMEIO_APP_TOKEN: Your app token
   - OAUTH_CLIENT_ID: Your OAuth client ID
   - OAUTH_CLIENT_SECRET: Your OAuth client secret
   - OAUTH_REDIRECT_URI: Your OAuth callback URL
   - ACTION_SECRET: Your custom action secret
   - AWS_REGION: AWS region (default: us-east-1)
   - DYNAMODB_TABLE_NAME: DynamoDB table name (default: frameio-user-tokens)

3. Ensure AWS credentials are configured:
   - Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables, OR
   - Use IAM role (recommended for EC2/ECS/Lambda), OR
   - Configure ~/.aws/credentials
"""

import os

import uvicorn
from frameio_kit import ActionEvent, App, DynamoDBTokenStore, Message

# Initialize DynamoDB token store
token_store = DynamoDBTokenStore(
    table_name=os.getenv("DYNAMODB_TABLE_NAME", "frameio-user-tokens"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    # Optional: Set TTL for automatic token cleanup after 90 days
    enable_ttl=True,
    ttl_days=90,
)

# Initialize the app with OAuth configuration
app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri=os.getenv("OAUTH_REDIRECT_URI"),
    token_store=token_store,
)


@app.on_action(
    event_type="create.proxy",
    name="Create Proxy",
    description="Create a proxy version of this asset in your account",
    secret=os.getenv("ACTION_SECRET"),
)
async def create_proxy(event: ActionEvent):
    """Create a proxy version of an asset on behalf of the user.

    This action demonstrates:
    - OAuth user authorization flow
    - Making API calls with user permissions
    - Error handling for authorization issues
    """
    print(f"📥 Proxy creation requested by user {event.user.id} for asset {event.resource_id}")

    # Check if user has authorized
    try:
        user_token = await app.oauth.get_user_token(event.user.id)
    except RuntimeError:
        user_token = None

    if not user_token:
        # User needs to authorize
        print(f"⚠️  User {event.user.id} needs to authorize")

        auth_url = app.oauth.get_authorization_url(state=f"{event.user.id}:{event.interaction_id}")

        return Message(
            title="Authorization Required",
            description=f"To create proxies, we need permission to access your Frame.io account.\n\n"
            f"Please visit this URL to authorize: {auth_url}\n\n"
            f"After authorizing, trigger this action again.",
        )

    # User is authorized - proceed with proxy creation
    print(f"✅ User {event.user.id} is authorized")

    try:
        # Create a client authenticated as the user
        user_client = await app.get_user_client(event.user.id)

        # Get the original asset
        asset = await user_client.assets.get(account_id=event.account_id, asset_id=event.resource_id)

        print(f"📄 Retrieved asset: {asset.name}")

        # In a real implementation, you would:
        # 1. Download the original file
        # 2. Create a proxy version (transcode, resize, etc.)
        # 3. Upload the proxy back to Frame.io
        # 4. Link it to the original asset

        # For demonstration, we'll just show what we would do:
        print(f"🎬 Would create proxy for: {asset.name}")
        print(f"   Type: {asset.type}")
        print(f"   Size: {asset.filesize if hasattr(asset, 'filesize') else 'N/A'}")

        return Message(
            title="Proxy Creation Started",
            description=f"Started creating proxy for '{asset.name}'.\n"
            f"You'll receive a notification when it's ready.",
        )

    except Exception as e:
        print(f"❌ Error creating proxy: {e}")

        # Check if it's an authorization error
        if "401" in str(e) or "Unauthorized" in str(e):
            # Token might be expired - prompt for re-authorization
            auth_url = app.oauth.get_authorization_url(state=f"{event.user.id}:{event.interaction_id}")

            return Message(
                title="Re-authorization Required",
                description=f"Your authorization has expired. Please authorize again: {auth_url}",
            )

        return Message(
            title="Error Creating Proxy",
            description=f"Failed to create proxy: {str(e)}\n\nPlease try again or contact support.",
        )


@app.on_action(
    event_type="check.auth",
    name="Check Authorization",
    description="Check if you've authorized this app",
    secret=os.getenv("ACTION_SECRET"),
)
async def check_authorization(event: ActionEvent):
    """Simple action to check if a user has authorized the app."""
    user_token = await app.oauth.get_user_token(event.user.id)

    if user_token:
        return Message(
            title="✅ Authorized",
            description="You have authorized this app. You can use all features!",
        )
    else:
        auth_url = app.oauth.get_authorization_url(state=f"{event.user.id}:{event.interaction_id}")

        return Message(
            title="❌ Not Authorized",
            description=f"You haven't authorized this app yet.\n\n"
            f"Authorize here: {auth_url}\n\n"
            f"Then check again!",
        )


if __name__ == "__main__":
    print("🚀 Starting Frame.io App with DynamoDB Storage")
    print(f"📍 DynamoDB Table: {os.getenv('DYNAMODB_TABLE_NAME', 'frameio-user-tokens')}")
    print(f"🌍 AWS Region: {os.getenv('AWS_REGION', 'us-east-1')}")
    print(f"📍 OAuth Callback: {os.getenv('OAUTH_REDIRECT_URI')}\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
