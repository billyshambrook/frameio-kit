"""User Authentication Example

This example demonstrates how to use Adobe Login OAuth to authenticate users
and make API calls on their behalf.

Prerequisites:
1. Create an OAuth Web App credential in Adobe Developer Console
2. Set environment variables for OAuth configuration
3. Configure a custom action in Frame.io workspace

Environment Variables:
- ADOBE_CLIENT_ID: Your Adobe IMS client ID
- ADOBE_CLIENT_SECRET: Your Adobe IMS client secret
- REDIRECT_URI: Your OAuth callback URL (e.g., https://yourapp.com/.auth/callback)
- ACTION_SECRET: Your Frame.io custom action secret
- FRAMEIO_AUTH_ENCRYPTION_KEY: Encryption key for tokens (optional)

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000

Then:
1. Expose via ngrok: ngrok http 8000
2. Update REDIRECT_URI to match your ngrok URL
3. Configure custom action in Frame.io to point to your ngrok URL
4. Click the action in Frame.io - you'll be prompted to login
5. After login, the action will execute with your user credentials
"""

import os

import uvicorn
from frameio_kit import ActionEvent, App, Client, Message, OAuthConfig
from key_value.aio.stores.disk import DiskStore

# Initialize app with OAuth configuration
app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:8000/.auth/callback"),
        # Persist tokens to disk so users don't need to re-authenticate on restart
        storage=DiskStore(directory="./tokens"),
        # Optional: Provide explicit encryption key
        encryption_key=os.getenv("FRAMEIO_AUTH_ENCRYPTION_KEY"),
    )
)


@app.on_action(
    event_type="userauth.process_file",
    name="Process File (User Auth)",
    description="Process a file using your Frame.io credentials",
    secret=os.getenv("ACTION_SECRET"),
    require_user_auth=True,  # Enable user authentication
)
async def process_file_as_user(event: ActionEvent):
    """Process a file using the authenticated user's credentials.

    This action requires the user to sign in with Adobe Login.
    API calls are made with the user's token, so activity logs
    will show the user's name instead of the app name.
    """
    # Create a client with the user's access token
    user_client = Client(token=event.user_access_token)

    # Fetch file details using the user's credentials
    file_response = await user_client.files.show(account_id=event.account_id, file_id=event.resource_id)

    file_data = file_response.data

    # Close the client when done
    await user_client.close()

    # Return a message to the user
    return Message(
        title=f"Processed {file_data.name}",
        description=f"""
File processed successfully using your credentials!

**Details:**
- File: {file_data.name}
- Size: {file_data.filesize:,} bytes
- User: {event.user_id}
- Type: {file_data.filetype or "Unknown"}

All API calls were made as you, so they'll appear under your name in Frame.io activity logs.
        """.strip(),
    )


@app.on_action(
    event_type="userauth.get_projects",
    name="List My Projects",
    description="List all projects you have access to",
    secret=os.getenv("ACTION_SECRET"),
    require_user_auth=True,
)
async def list_user_projects(event: ActionEvent):
    """List all projects the authenticated user has access to."""
    user_client = Client(token=event.user_access_token)

    # Get user's projects
    projects_response = await user_client.projects.list(account_id=event.account_id)

    await user_client.close()

    if not projects_response.data:
        return Message(title="No Projects Found", description="You don't have access to any projects.")

    # Format project list
    project_list = "\n".join([f"- {project.name}" for project in projects_response.data[:10]])

    total = len(projects_response.data)
    if total > 10:
        project_list += f"\n\n...and {total - 10} more"

    return Message(
        title=f"Your Projects ({total} total)",
        description=f"Here are the projects you have access to:\n\n{project_list}",
    )


if __name__ == "__main__":
    # Validate environment variables
    required_vars = ["ADOBE_CLIENT_ID", "ADOBE_CLIENT_SECRET", "ACTION_SECRET"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following environment variables:")
        print("  - ADOBE_CLIENT_ID")
        print("  - ADOBE_CLIENT_SECRET")
        print("  - REDIRECT_URI (optional, defaults to http://localhost:8000/.auth/callback)")
        print("  - ACTION_SECRET")
        print("  - FRAMEIO_AUTH_ENCRYPTION_KEY (optional)")
        exit(1)

    print("✅ Starting Frame.io app with user authentication")
    print(f"📍 OAuth callback URL: {os.getenv('REDIRECT_URI', 'http://localhost:8000/.auth/callback')}")
    print("💾 Token storage: ./tokens")
    print()
    print("OAuth endpoints:")
    print("  - Login: http://localhost:8000/.auth/login")
    print("  - Callback: http://localhost:8000/.auth/callback")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)
