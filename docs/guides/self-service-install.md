# Self-Service Installation

Self-service installation pages for workspace admins. Auto-discovers handlers from decorators, creates webhooks and custom actions via the Frame.io API, and manages signing secrets — all with a branded UI.

## When to Use

**Use the installation system when you need to:**

- Deploy a multi-tenant app across multiple workspaces and accounts
- Provide a self-service UI for workspace admins to install your integration
- Automatically manage webhook and custom action lifecycle (create, update, uninstall)
- Eliminate manual API registration and secret management

**For single-workspace or development setups, static secrets with environment variables are sufficient.**

## Quick Start

### 1. Install the Optional Dependency

```bash
pip install frameio-kit[install]
```

### 2. Configure Your App

```python
import os
from frameio_kit import App, OAuthConfig

app = App(
    oauth=OAuthConfig(
        client_id=os.environ["ADOBE_CLIENT_ID"],
        client_secret=os.environ["ADOBE_CLIENT_SECRET"],
    ),
    install=True,
    name="Transcription Bot",
    description="Automatically transcribes videos uploaded to Frame.io.",
    primary_color="#6366f1",
)

# Handlers are auto-discovered — no secret parameter needed
@app.on_webhook("file.ready")
async def on_file_ready(event):
    ...

@app.on_action("myapp.transcribe", name="Transcribe", description="Transcribe video audio")
async def on_transcribe(event):
    ...
```

That's it. Run with `uvicorn` and visit `/install` — the branded installation page is automatically available.

!!! note "No Secret Parameter Needed"

    When `install=True`, signing secrets are automatically resolved from installation records. You don't need to pass `secret` to `@app.on_webhook` or `@app.on_action`.

!!! warning "Storage"

    Using `MemoryStorage` (the default) means installation records are lost on app restart. Use `DynamoDBStorage` or a custom `Storage` implementation for production deployments.

### 3. Register the Callback URL

In the [Adobe Developer Console](https://developer.adobe.com/), add `https://yourapp.com/install/callback` as a redirect URL for your OAuth credential.

## How It Works

1. **At startup**: The system introspects registered `@app.on_webhook` and `@app.on_action` handlers to build a **handler manifest** — a description of what needs to be installed.

2. **Admin visits `/install`**: A branded landing page shows your app name, description, and what will be installed (webhook events, custom actions).

3. **OAuth flow**: Admin clicks "Login with Adobe" → authenticates → selects an account and workspace.

4. **Install**: The system uses the admin's OAuth token to call the Frame.io API:
    - Creates a **consolidated webhook** for all webhook event types
    - Creates **individual custom actions** for each action handler
    - Stores the returned **signing secrets** (encrypted at rest) in your Storage backend

5. **Events arrive**: When Frame.io sends events, the `InstallationSecretResolver` automatically looks up the correct signing secret from the installation record — no manual configuration needed.

## User Journeys

### Installing

1. Workspace admin navigates to `https://yourapp.com/install`
2. Sees branded landing page with app description and what will be installed
3. Clicks "Login with Adobe" → OAuth flow
4. Selects account and workspace from dropdowns
5. Clicks "Install" → webhooks and custom actions are created
6. Success confirmation shown

### Updating

When you change handlers in code (add/remove webhooks or actions, rename an action) and redeploy:

1. Admin visits `/install`, authenticates, selects their workspace
2. Status panel shows "Update Available" with a diff summary:
    - `+ Webhook event: comment.created`
    - `+ Action: "Export to S3"`
    - `- Action: "Old Export" (will be removed)`
    - `~ Action: "Transcribe" (description updated)`
3. Admin clicks "Update"
4. System performs targeted API calls — only creating, deleting, or patching what changed

!!! note "Secrets Survive Updates"

    Frame.io only returns signing secrets at creation time. The system preserves existing secrets for updated resources and only assigns fresh secrets to newly created ones.

### Uninstalling

1. Admin visits `/install`, selects workspace, sees current installation
2. Clicks "Uninstall" → all webhooks and custom actions are deleted
3. Installation records removed from Storage

## Configuration Reference

These parameters are passed directly to `App(...)`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `install` | `bool` | `False` | Enable the self-service install page |
| `install_fields` | `list[InstallField] \| None` | `None` | Configuration fields shown during install |
| `name` | `str \| None` | `None` | Display name in install UI and auth pages |
| `description` | `str` | `""` | Description shown on landing page |
| `logo_url` | `str \| None` | `None` | Partner logo URL |
| `primary_color` | `str` | `"#6366f1"` | Branding primary color (hex) |
| `accent_color` | `str` | `"#8b5cf6"` | Branding accent color (hex) |
| `custom_css` | `str \| None` | `None` | Raw CSS injected into templates |
| `show_powered_by` | `bool` | `True` | Show "Powered by frameio-kit" footer |
| `base_url` | `str \| None` | `None` | Public URL override (else inferred from request) |
| `allowed_accounts` | `list[str] \| None` | `None` | Account IDs allowed to install (None = all) |
| `install_session_ttl` | `int` | `1800` | Install session TTL in seconds (30 min) |

## Branding

Customize the installation pages with your brand identity:

```python
app = App(
    oauth=OAuthConfig(...),
    install=True,
    name="My Video Tool",
    description="AI-powered video analysis for your team.",
    logo_url="https://myapp.com/logo.png",
    primary_color="#1a73e8",
    accent_color="#34a853",
    custom_css=".fk-header { font-family: 'Inter', sans-serif; }",
    show_powered_by=False,
)
```

The UI uses CSS custom properties (`--fk-primary`, `--fk-accent`, etc.) derived from your configuration, combined with Tailwind CSS for layout and spacing.

## Restricting Access

By default, any Frame.io user who authenticates can install the app to any account they belong to. To restrict installation to specific accounts, use `allowed_accounts`:

```python
app = App(
    oauth=OAuthConfig(...),
    install=True,
    name="Internal Tool",
    allowed_accounts=[
        "12345678-1234-1234-1234-123456789abc",  # Production account
    ],
)
```

When set, only the listed accounts appear in the account dropdown and install/uninstall requests for other accounts are rejected. This is useful for internal tools that should only run within your own organization's accounts.

## Custom Install Fields

Collect additional configuration from workspace admins during installation — such as API keys, endpoint URLs, or environment selection.

### Declaring Fields

Pass a list of `InstallField` declarations to `App`:

```python
from frameio_kit import App, OAuthConfig, InstallField

app = App(
    oauth=OAuthConfig(...),
    install=True,
    name="My Integration",
    install_fields=[
        InstallField(
            name="api_key",
            label="API Key",
            type="password",
            required=True,
            description="Your service API key",
        ),
        InstallField(
            name="environment",
            label="Environment",
            type="select",
            options=("production", "staging"),
            default="production",
        ),
        InstallField(
            name="endpoint_url",
            label="Endpoint URL",
            type="text",
            description="Custom endpoint URL",
        ),
        InstallField(
            name="notes",
            label="Notes",
            type="textarea",
        ),
    ],
)
```

### Field Types

| Type | HTML Element | Notes |
|------|-------------|-------|
| `text` | `<input type="text">` | Default type |
| `password` | `<input type="password">` | Auto-sets `sensitive=True` — value encrypted at rest |
| `select` | `<select>` | Requires `options` tuple |
| `textarea` | `<textarea>` | Multi-line text input |

### InstallField Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | *required* | Machine-readable key used in the config dict |
| `label` | `str` | *required* | Human-readable label shown in the UI |
| `type` | `str` | `"text"` | Field type: `text`, `password`, `select`, or `textarea` |
| `required` | `bool` | `False` | Whether the field must be filled in |
| `description` | `str` | `""` | Help text shown below the field |
| `options` | `tuple[str, ...]` | `()` | Choices for `select` fields |
| `default` | `str` | `""` | Default value pre-filled in the form |
| `sensitive` | `bool \| None` | `None` | Encrypt at rest. `None` = auto (`True` for `password`) |

!!! note "Reserved Names"

    Field names `account_id` and `workspace_id` are reserved and cannot be used.

### Accessing Config in Handlers

Use `get_install_config()` to retrieve config values within webhook and action handlers:

```python
from frameio_kit import get_install_config

@app.on_webhook("file.ready")
async def on_file_ready(event):
    config = get_install_config()
    api_key = config["api_key"]
    env = config["environment"]
    # Use the values...
```

The config dict maps field names to their string values (HTML forms always submit strings).

!!! warning

    `get_install_config()` raises `RuntimeError` if called outside a handler context, or if the app has no `install_fields`, or if no installation exists for the event's workspace.

### Sensitive Fields

Fields with `sensitive=True` (or `type="password"`, which implies it) are encrypted at rest using the same Fernet encryption as signing secrets.

In the install UI:

- **New install**: The field renders as a normal password input
- **Installed state**: Shows "Configured" instead of the actual value
- **Edit/Update**: Shows an empty password field with placeholder "(unchanged)" — submitting an empty value preserves the existing secret

### Config on Updates

When an admin updates an installation, config values are merged:

- Non-sensitive fields are replaced with the new values
- Empty sensitive fields preserve the existing value (standard password-field UX)
- Non-empty sensitive fields are replaced with the new value

## Storage

Installation data uses the same `Storage` backend as OAuth token management. Records are keyed by `install:{account_id}:{workspace_id}`.

### Development: MemoryStorage

```python
# Default — no storage parameter needed
app = App(
    oauth=OAuthConfig(...),
    install=True,
    name="My App",
)
```

### Production: DynamoDBStorage

Install the optional dependencies:

```bash
pip install frameio-kit[install,dynamodb]
```

```python
from frameio_kit import DynamoDBStorage

storage = DynamoDBStorage(table_name="frameio-app-data")

app = App(
    oauth=OAuthConfig(...),
    storage=storage,
    install=True,
    name="My App",
)
```

## Routes

The installation system mounts these routes:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/install` | Landing page |
| `GET` | `/install/login` | Initiate OAuth for install |
| `GET` | `/install/callback` | Handle OAuth callback |
| `GET` | `/install/workspaces` | HTMX: load workspaces for selected account |
| `GET` | `/install/status` | HTMX: installation status for selected workspace |
| `POST` | `/install/execute` | HTMX: perform install or update |
| `POST` | `/install/uninstall` | HTMX: perform uninstall |

## Security

- **Secrets encrypted at rest** — Signing secrets and sensitive config values are encrypted with Fernet (AES-128 + HMAC) before storage
- **Session encryption** — OAuth access tokens in install sessions are also encrypted
- **Signed cookies** — Session cookies are cryptographically signed with `HttpOnly`, `Secure`, `SameSite=Lax`, and `Path=/install`
- **Input validation** — Account and workspace IDs are validated as UUIDs; required config fields are validated before install
- **Auto-escaping** — Jinja2 templates use `autoescape=True` to prevent XSS
- **Config context isolation** — Install config is set in request-scoped context after signature verification, never before

!!! warning "URL Inference"

    When `base_url` is not set, the public URL for webhooks is inferred from the request's `Host` header. Set `base_url` explicitly in production, especially behind reverse proxies.

## Best Practices

- Always use persistent storage (e.g., `DynamoDBStorage`) in production
- Set `base_url` explicitly when behind a reverse proxy
- Test the install flow in development using [ngrok](https://ngrok.com/) or similar
- The installing user needs workspace admin access in Frame.io

## Next Steps

- [User Authentication](user-auth.md) — OAuth for user-specific API calls
- [Custom Actions](custom-actions.md) — Build interactive workflows
- [Webhooks](webhooks.md) — React to Frame.io events
- [API Reference](../reference/api.md) — Complete type documentation
