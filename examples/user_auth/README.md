# User Authentication Example

This example demonstrates how to build a Frame.io app that uses Adobe Login OAuth to authenticate users and make API calls on their behalf.

## What This Example Shows

- Configuring Adobe IMS OAuth in your app
- Requiring user authentication for specific actions
- Making API calls with user credentials
- Persisting tokens to disk for session continuity
- Accessing user-specific data

## Prerequisites

1. **Adobe Developer Console Setup**:
   - Create a project in [Adobe Developer Console](https://developer.adobe.com/)
   - Add the "Frame.io API" service
   - Create an "OAuth Web App" credential
   - Note your Client ID and Client Secret
   - Add your callback URL to allowed redirect URIs

2. **Frame.io Workspace**:
   - Access to a Frame.io workspace
   - Permission to create custom actions

3. **Development Tools**:
   - Python 3.13+
   - ngrok (for local development)

## Setup

### 1. Install Dependencies

```bash
cd examples/user_auth
pip install frameio-kit uvicorn
```

### 2. Configure Environment Variables

Create a `.env` file:

```bash
# Adobe IMS OAuth Configuration
ADOBE_CLIENT_ID=your_adobe_client_id
ADOBE_CLIENT_SECRET=your_adobe_client_secret
REDIRECT_URI=http://localhost:8000/.auth/callback

# Frame.io Action Secret
ACTION_SECRET=your_frameio_action_secret

# Optional: Explicit encryption key for tokens
FRAMEIO_AUTH_ENCRYPTION_KEY=your_encryption_key
```

To generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Start ngrok

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`).

### 4. Update OAuth Callback URL

1. In Adobe Developer Console, add `https://abc123.ngrok-free.app/.auth/callback` to allowed redirect URIs
2. Update your `.env` file:
   ```bash
   REDIRECT_URI=https://abc123.ngrok-free.app/.auth/callback
   ```

### 5. Configure Frame.io Custom Actions

Create two custom actions in your Frame.io workspace:

**Action 1: Process File (User Auth)**
- Name: `Process File (User Auth)`
- Description: `Process a file using your Frame.io credentials`
- Event Type: `userauth.process_file`
- URL: `https://abc123.ngrok-free.app`
- Copy the signing secret to `ACTION_SECRET` in `.env`

**Action 2: List My Projects**
- Name: `List My Projects`
- Description: `List all projects you have access to`
- Event Type: `userauth.get_projects`
- URL: `https://abc123.ngrok-free.app`
- Use the same signing secret

### 6. Run the App

```bash
python main.py
```

You should see:

```
✅ Starting Frame.io app with user authentication
📍 OAuth callback URL: https://abc123.ngrok-free.app/.auth/callback
💾 Token storage: ./tokens

OAuth endpoints:
  - Login: http://localhost:8000/.auth/login
  - Callback: http://localhost:8000/.auth/callback
```

## Usage

### First Time (Authentication Required)

1. In Frame.io, right-click any file
2. Select "Process File (User Auth)"
3. You'll see a "Sign in with Adobe" button
4. Click it to start the OAuth flow
5. Sign in with your Adobe credentials
6. Authorize the app
7. You'll be redirected back and the action will execute

### Subsequent Uses

After authenticating once, you won't be prompted to login again (tokens are persisted to `./tokens`).

## How It Works

### 1. App Initialization

```python
app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("ADOBE_CLIENT_ID"),
        client_secret=os.getenv("ADOBE_CLIENT_SECRET"),
        redirect_uri=os.getenv("REDIRECT_URI"),
        storage=DiskStore(directory="./tokens"),
    )
)
```

This configures OAuth with token persistence.

### 2. Action with User Auth

```python
@app.on_action(
    ...,
    require_user_auth=True,  # Enable user authentication
)
async def process_file_as_user(event: ActionEvent):
    # User's token is available here
    user_client = Client(token=event.user_access_token)
    ...
```

Setting `require_user_auth=True` triggers automatic authentication checks.

### 3. Using User Credentials

```python
# Create client with user's token
user_client = Client(token=event.user_access_token)

# Make API calls as the user
file = await user_client.files.show(...)
```

All API calls are attributed to the authenticated user in Frame.io activity logs.

## What You'll See

### In Frame.io UI

- First time: "Sign in with Adobe" button
- Subsequent times: Action executes immediately
- Success message with file/project details

### In Activity Logs

- API calls appear under your user name (not the app)
- Proper user attribution for all actions

### In Terminal

```
INFO:     Started server process
INFO:     Waiting for application startup
✅ Starting Frame.io app with user authentication
...
```

## Token Storage

Tokens are stored in `./tokens/` directory:

```
tokens/
  user:user_abc123    # Encrypted token for user_abc123
  user:user_xyz789    # Encrypted token for user_xyz789
```

Each token is encrypted using Fernet symmetric encryption.

## Troubleshooting

### "Invalid signature" error

- Verify `ACTION_SECRET` matches the secret from Frame.io
- Ensure ngrok URL is correct in Frame.io action configuration

### Redirect URI mismatch

- Check `REDIRECT_URI` exactly matches Adobe Console configuration
- Must include `/.auth/callback` path
- Must use HTTPS (except localhost)

### Tokens not persisting

- Ensure `./tokens` directory exists and is writable
- Check encryption key is consistent across restarts

### User repeatedly asked to login

- Verify token storage is working (check `./tokens/` directory)
- Ensure encryption key is set consistently

## Next Steps

- Review the [User Authentication Guide](../../docs/usage/user_auth.md) for details
- Try mixing S2S and user auth in the same app
- Implement token deletion for user logout
- Add Redis storage for multi-server deployments

## Security Notes

- **Never commit** `.env` file or `tokens/` directory
- Use HTTPS in production (required by Adobe)
- Rotate encryption keys periodically
- Store secrets securely (use secret managers in production)
