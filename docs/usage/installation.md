# App Installation System

The app installation system enables partner apps to be installed into multiple Frame.io workspaces without manual configuration. The system automatically creates custom actions and webhooks via the Frame.io APIs, manages signing secrets per workspace, and provides a self-service installation UI for end users.

## Overview

When you enable the installation system, your app will:

- **Auto-discover** registered action and webhook handlers
- **Generate** an installation manifest describing what will be installed
- **Provide** a self-service UI at `/install` for users to install your app
- **Create** custom actions and webhooks in Frame.io workspaces automatically
- **Manage** workspace-specific signing secrets securely
- **Support** multiple workspace installations (multi-tenant ready)

## Quick Start

Here's a minimal example of enabling installation:

```python
from frameio_kit import App, OAuthConfig, InstallationConfig
from key_value.aio.stores.disk import DiskStore

app = App(
    token="your-service-account-token",
    oauth=OAuthConfig(
        client_id="your-adobe-client-id",
        client_secret="your-adobe-client-secret",
        base_url="https://your-app.com",
        storage=DiskStore("./storage"),
        encryption_key="your-encryption-key",
    ),
    installation=InstallationConfig(
        enabled=True,
        app_name="My Awesome App",
        app_description="Process files and add comments automatically",
        app_icon_url="https://your-app.com/icon.png",
    ),
)

# Register handlers as normal - they'll be auto-discovered
@app.on_action(
    event_type="my_app.transcribe",
    name="Transcribe Video",
    description="Generate transcript from video file",
    secret="placeholder-will-be-overridden",
)
async def transcribe(event):
    return Message(title="Transcribing...", description="This will take a moment")

@app.on_webhook(
    event_type="file.ready",
    secret="placeholder-will-be-overridden",
)
async def on_file_ready(event):
    # Process file
    pass
```

## Installation Flow

### User Experience

1. **Landing Page** - User visits `https://your-app.com/install`
   - Sees app name, description, and icon
   - Sees list of custom actions and webhooks that will be installed
   - Clicks "Install to Frame.io" button

2. **OAuth Flow** - User authenticates with Adobe IMS
   - Redirects to Adobe login
   - User signs in with their Frame.io account
   - Redirects back to your app

3. **Workspace Selection** - User selects workspaces
   - Shows all workspaces user has access to
   - User selects one or more workspaces with checkboxes
   - Clicks "Install Selected" button

4. **Installation** - App installs to selected workspaces
   - Creates custom actions via experimental API
   - Creates webhooks via standard API
   - Generates unique secrets per workspace
   - Stores installation records securely

5. **Success** - User sees confirmation
   - Shows which workspaces were installed successfully
   - Shows any errors that occurred
   - User returns to Frame.io to use the app

## Configuration

### Installation Config

```python
InstallationConfig(
    enabled=True,  # Enable installation feature
    app_name="My App",  # Display name
    app_description="What your app does",  # Description
    app_icon_url="https://example.com/icon.png",  # Optional icon URL

    # Optional: Filter what gets installed
    include_actions=["my_app.transcribe", "my_app.translate"],  # Only these actions
    include_webhooks=["file.ready", "comment.created"],  # Only these webhooks
)
```

### OAuth Requirement

Installation **requires** OAuth to be configured because:

- User authentication is needed to create resources in Frame.io
- User tokens are used to make API calls on behalf of the user
- Token storage is needed for managing installations

## Secret Management

When installation is enabled, the secrets provided in decorator registration are **ignored**. Instead:

1. During installation, unique secrets are generated per workspace
2. Secrets are stored encrypted in storage with key: `install:{workspace_id}`
3. When events arrive, the app looks up the workspace-specific secret for signature verification

### Secret Lookup Flow

```python
# Automatic - handled internally by frameio_kit
def verify_event(request):
    workspace_id = extract_workspace_id(request.body)

    # Try workspace-specific secret first
    secret = storage.get(f"install:{workspace_id}:secret:{event_type}")

    # Fall back to decorator-provided secret for backwards compatibility
    if not secret:
        secret = get_decorator_secret(event_type)

    verify_signature(request, secret)
```

### Backwards Compatibility

Existing apps without installation enabled continue to work exactly as before:
- Secrets from decorators are used
- No installation routes are added
- No installation manager is created

## Managing Installations

### List Installations

```python
# List all installations for a user
installations = await app.installation_manager.list_installations(user_id="user_123")

for installation in installations:
    print(f"Workspace: {installation.workspace_id}")
    print(f"Actions: {len(installation.actions)}")
    print(f"Webhooks: {len(installation.webhooks)}")
    print(f"Installed: {installation.installed_at}")
```

### Get Specific Installation

```python
# Get installation for a specific workspace
installation = await app.installation_manager.get_installation(workspace_id="workspace_123")

if installation:
    print(f"Status: {installation.status}")
    print(f"Account ID: {installation.account_id}")
```

### Programmatic Installation

```python
# Install programmatically (if needed)
result = await app.installation_manager.install(
    user_id="user_123",
    user_token="user_oauth_token",
    workspace_ids=["workspace_123", "workspace_456"],
)

if result.success:
    print(f"Installed to {len(result.workspace_results)} workspaces")
else:
    for workspace_id, error in result.errors.items():
        print(f"Failed for {workspace_id}: {error}")
```

### Programmatic Uninstall

```python
# Uninstall from workspaces
result = await app.installation_manager.uninstall(
    user_id="user_123",
    user_token="user_oauth_token",
    workspace_ids=["workspace_123"],
)
```

## API Endpoints

When installation is enabled, the following routes are automatically added:

- `GET /install` - Installation landing page
- `GET /install/oauth/login` - OAuth initiation for installation
- `GET /auth/callback` - OAuth callback
- `GET /install/workspaces` - Workspace selection page
- `POST /install/process` - Process installation
- `GET /install/manage` - Manage existing installations
- `POST /install/uninstall` - Uninstall from workspace

## Storage Schema

### Installation Record

Storage Key: `install:{workspace_id}`

```python
{
    "workspace_id": "ws_123",
    "account_id": "acc_456",
    "user_id": "user_789",
    "installed_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z",
    "status": "active",
    "actions": [
        {
            "action_id": "action_abc",
            "event_type": "my_app.transcribe",
            "name": "Transcribe Video",
            "description": "Generate transcript",
            "secret": "encrypted_secret_xyz",
            "created_at": "2025-01-15T10:30:00Z"
        }
    ],
    "webhooks": [
        {
            "webhook_id": "webhook_def",
            "event_types": ["file.ready"],
            "name": "File Ready Handler",
            "secret": "encrypted_secret_abc",
            "created_at": "2025-01-15T10:30:00Z"
        }
    ],
    "manifest_version": "a1b2c3d4"
}
```

### User Installation Index

Storage Key: `install:index:{user_id}`

```python
{
    "user_id": "user_789",
    "workspace_ids": ["ws_123", "ws_456"],
    "updated_at": "2025-01-15T10:30:00Z"
}
```

## Multi-Tenant Architecture

The installation system is designed for multi-tenant applications:

### Workspace Isolation

```
Workspace A:
  ├── Action "transcribe" → secret_A1
  ├── Action "translate" → secret_A2
  └── Webhook "file.ready" → secret_A3

Workspace B:
  ├── Action "transcribe" → secret_B1  (different from A1)
  ├── Action "translate" → secret_B2  (different from A2)
  └── Webhook "file.ready" → secret_B3  (different from A3)
```

### Benefits

- **Workspace compromise doesn't affect other workspaces**
- **Easier audit trail per workspace**
- **Can revoke access per workspace**
- **Independent scaling per workspace**

## Security

### Secret Generation

- Cryptographically secure random secrets using `secrets.token_urlsafe(32)`
- One unique secret per action per workspace
- One unique secret per webhook per workspace
- Secrets encrypted at rest using Fernet encryption

### OAuth Scopes

Installation flow requires OAuth with these scopes:

- `openid` - User identification
- `profile` - User profile info
- `offline_access` - Refresh token
- `additional_info.roles` - Workspace access verification

### Event Verification

When events arrive:

1. Extract `workspace_id` from event payload
2. Look up installation record: `install:{workspace_id}`
3. Find corresponding secret for the event type
4. Verify signature using workspace-specific secret
5. Reject if signature invalid or installation not found

## Customization

### Filtering What Gets Installed

```python
# Only install specific actions
InstallationConfig(
    enabled=True,
    app_name="My App",
    app_description="Does cool things",
    include_actions=["my_app.transcribe", "my_app.translate"],
    # All webhooks will be installed
)

# Only install specific webhooks
InstallationConfig(
    enabled=True,
    app_name="My App",
    app_description="Does cool things",
    # All actions will be installed
    include_webhooks=["file.ready", "comment.created"],
)
```

### Custom Installation UI

The installation UI uses simple HTML templates that can be customized by modifying `_install_ui.py`. Future versions may support custom templates.

## Troubleshooting

### Installation Failed

If installation fails for a workspace:

- Check that the user has permission to create custom actions in that workspace
- Check that the user has permission to create webhooks in that workspace
- Check the Frame.io API limits and quotas
- Check the error message in `result.errors[workspace_id]`

### Events Not Being Received

If events aren't being received after installation:

- Verify the installation record exists: `await app.installation_manager.get_installation(workspace_id)`
- Check that the webhook/action was created in Frame.io
- Check the Frame.io webhook/action configuration
- Verify signature validation is working

### OAuth Errors

If OAuth flow fails:

- Verify `base_url` matches your actual app URL
- Verify OAuth credentials are correct
- Check that `{base_url}/install/oauth/callback` is registered in Adobe Console
- Check token storage is working

## Example: Full Installation Setup

```python
import os
from frameio_kit import App, OAuthConfig, InstallationConfig
from key_value.aio.stores.disk import DiskStore

# Setup app with installation
app = App(
    token=os.getenv("FRAMEIO_SERVICE_TOKEN"),
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        base_url=os.getenv("APP_BASE_URL", "https://my-app.com"),
        storage=DiskStore("./storage"),
        encryption_key=os.getenv("ENCRYPTION_KEY"),
    ),
    installation=InstallationConfig(
        enabled=True,
        app_name="Video Processor",
        app_description="Automatically transcribe and translate videos",
        app_icon_url="https://my-app.com/icon.png",
    ),
)

# Register handlers - they'll be auto-discovered
@app.on_action(
    event_type="video_processor.transcribe",
    name="Transcribe Video",
    description="Generate transcript from video file",
    secret="placeholder",
)
async def transcribe(event):
    # Process transcription
    return Message(
        title="Transcription Started",
        description=f"Processing file: {event.resource_id}",
    )

@app.on_webhook(
    event_type="file.ready",
    secret="placeholder",
)
async def on_file_ready(event):
    # Auto-process new files
    pass

# Run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Users can now visit `https://my-app.com/install` to install your app to their Frame.io workspaces!
