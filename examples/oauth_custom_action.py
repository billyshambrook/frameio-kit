"""Example: Custom Action with OAuth User Authorization

This example demonstrates how to create a custom action that requires user
authorization to perform actions on behalf of the user.

Setup:
1. Set environment variables:
   - FRAMEIO_APP_TOKEN: Your app token for basic API calls
   - OAUTH_CLIENT_ID: Your OAuth client ID from Frame.io Developer Console
   - OAUTH_CLIENT_SECRET: Your OAuth client secret
   - OAUTH_REDIRECT_URI: Your OAuth callback URL (e.g., https://yourapp.com/oauth/callback)
   - ACTION_SECRET: Your custom action secret
   
2. Configure your Frame.io custom action to point to your server

How it works:
- When a user triggers the action for the first time, they'll be shown an authorization URL
- After authorization, the token is stored and subsequent actions will work automatically
- The app can then make API calls on behalf of the user

Note: This example uses InMemoryTokenStore for simplicity. For production, use
DynamoDBTokenStore or implement your own persistent storage.
"""

import os

import uvicorn
from frameio_kit import ActionEvent, App, InMemoryTokenStore, Message, RequireAuth

# Initialize the app with OAuth configuration
# For production, replace InMemoryTokenStore with DynamoDBTokenStore or your own implementation
app = App(
    token=os.getenv("FRAMEIO_APP_TOKEN"),
    oauth_client_id=os.getenv("OAUTH_CLIENT_ID"),
    oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    oauth_redirect_uri=os.getenv("OAUTH_REDIRECT_URI", "https://yourapp.com/oauth/callback"),
    token_store=InMemoryTokenStore(),
)


@app.on_action(
    event_type="export.to.service",
    name="Export to My Service",
    description="Export this asset to an external service with your credentials",
    secret=os.getenv("ACTION_SECRET", "your_action_secret"),
)
async def export_to_service(event: ActionEvent):
    """Custom action that exports an asset on behalf of the user.
    
    This action requires user authorization to access their Frame.io account.
    """
    print(f"📥 Action triggered by user {event.user.id} for asset {event.resource_id}")

    # Check if we have a token for this user
    try:
        user_token = await app.oauth.get_user_token(event.user.id)
    except RuntimeError:
        user_token = None

    if not user_token:
        # User hasn't authorized yet - simply return RequireAuth()
        # The framework automatically generates the auth URL and message
        print(f"⚠️  User {event.user.id} needs to authorize")

        return RequireAuth(
            description="To export assets, we need your permission to access your Frame.io account."
        )

    # User is authorized - perform the action with their token
    print(f"✅ User {event.user.id} is authorized, proceeding with export")

    try:
        # Create a client authenticated as the user
        user_client = await app.get_user_client(event.user.id)

        # Fetch the asset details using the user's token
        asset = await user_client.assets.get(account_id=event.account_id, asset_id=event.resource_id)

        # In a real application, you would export the asset to your service here
        # For example:
        # await my_service.upload_asset(
        #     name=asset.name,
        #     download_url=asset.download_url,
        #     user_id=event.user.id
        # )

        print(f"📤 Successfully exported asset: {asset.name}")

        return Message(
            title="Export Complete",
            description=f"Successfully exported '{asset.name}' to your service. "
            f"You'll receive a notification when processing is complete.",
        )

    except Exception as e:
        print(f"❌ Error exporting asset: {e}")
        return Message(
            title="Export Failed",
            description=f"Failed to export the asset: {str(e)}. Please try again or contact support.",
        )


if __name__ == "__main__":
    print("🚀 Starting Frame.io OAuth Example App")
    print(f"📍 OAuth callback URL: {os.getenv('OAUTH_REDIRECT_URI', 'https://yourapp.com/oauth/callback')}")
    print("\nMake sure to:")
    print("1. Set all required environment variables")
    print("2. Register the OAuth callback URL in Frame.io Developer Console")
    print("3. Configure your custom action to point to this server\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
