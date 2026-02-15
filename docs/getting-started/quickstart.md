# Quickstart

This guide takes you from zero to a working Frame.io integration in minutes. If you haven't installed frameio-kit yet, start with the [Installation](installation.md) page.

## What You'll Build

By the end of this guide, you'll have:

- A running Frame.io integration
- A custom action that responds to user clicks
- A webhook that processes file events

If you're not sure what webhooks and custom actions are, see the [Concepts](../concepts.md) page for an overview.

## Step 1: Create Your Application

Create a file named `main.py` with the following code:

```python
from frameio_kit import App, ActionEvent, WebhookEvent, Message

app = App()

# Custom Action: Responds to user clicks in Frame.io
# CUSTOM_ACTION_SECRET env var will be used automatically
@app.on_action(
    event_type="greeting.say_hello",
    name="Say Hello",
    description="A simple greeting action"
)
async def on_greeting(event: ActionEvent):
    print(f"Hello from {event.user.id}!")
    return Message(
        title="Greetings!",
        description="Hello from your first frameio-kit app!"
    )

# Webhook: Responds to file events from Frame.io
# WEBHOOK_SECRET env var will be used automatically
@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")
```

**What this code does:**

- **Custom Action** - Creates a "Say Hello" menu item in Frame.io that displays a greeting when clicked
- **Webhook** - Listens for `file.ready` events and prints the file ID when files are processed
- **`App()`** - Initializes your Frame.io integration
- **`Message`** - Returned from the custom action handler to display a response in the Frame.io UI
- **Environment Variables** - `CUSTOM_ACTION_SECRET` and `WEBHOOK_SECRET` are automatically loaded from environment

Learn more about [Custom Actions](../guides/custom-actions.md) and [Webhooks](../guides/webhooks.md).

## Step 2: Expose Your Server

Frame.io needs a public URL to send events to your application. For local development, use [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok-free.app`) -- you'll need it for Frame.io configuration.

## Step 3: Configure Frame.io

### Create a Custom Action

1. In Frame.io, navigate to **Account Settings > Actions**
2. Click **"New Action"** and configure:
   - **Name**: `Say Hello`
   - **Event**: `greeting.say_hello`
   - **URL**: Your ngrok URL
   - **Workspace**: Choose the workspace
3. Copy the signing secret

### Create a Webhook

1. In the same settings page, go to **Webhooks**
2. Click **"New Webhook"** and configure:
   - **Webhook Name**: On file ready
   - **Event Types**: Select `file.ready`
   - **Webhook URL**: Your ngrok URL
   - **Workspace**: Choose the workspace
3. Copy the signing secret

### Set Environment Variables

Create a `.env` file with the secrets from Frame.io:

```bash
CUSTOM_ACTION_SECRET=your-action-secret-here
WEBHOOK_SECRET=your-webhook-secret-here
```

!!! note "Secret Configuration"
    This example uses the default `CUSTOM_ACTION_SECRET` and `WEBHOOK_SECRET` environment variables, which is recommended when you have **one action and one webhook**.

    **For multiple secrets**: Pass each secret explicitly via environment variables:
    ```python
    @app.on_webhook("file.ready", secret=os.environ["FILES_WEBHOOK_SECRET"])
    @app.on_action("my_app.analyze", name="Analyze", description="Analyze file", secret=os.environ["ANALYZE_CUSTOM_ACTION_SECRET"])
    ```

    **For dynamic secrets** (e.g., multi-tenant apps, database-backed secrets): See [Secret Resolution Precedence](../guides/app.md#secret-resolution-precedence) in the App Configuration guide, or use the [Self-Service Installation System](../guides/self-service-install.md) for automatic secret management.

## Step 4: Run Your Application

Export the environment variables and start the server:

```bash
# Load environment variables
export CUSTOM_ACTION_SECRET=your-action-secret-here
export WEBHOOK_SECRET=your-webhook-secret-here

# Start the server
uvicorn main:app --reload
```

!!! tip "Using a .env file"
    The `.env` file you created in the previous step is for reference — `uvicorn` does not load it automatically. You can either export the variables manually as shown above, or use `uvicorn --env-file .env main:app --reload` to load them from the file.

## Step 5: Test Your Integration

**Test the Custom Action:**

1. Right-click any asset in Frame.io
2. Select "Say Hello" from the menu
3. See the greeting message appear

**Test the Webhook:**

1. Upload a file to Frame.io
2. Wait for it to reach "Ready" status
3. Check your terminal for the webhook message

## What You've Built

You now have a working Frame.io integration that:

- Responds to user clicks with custom actions
- Processes Frame.io events with webhooks
- Returns feedback to users in the Frame.io UI
- Verifies requests with signature authentication

## Next Steps

Explore more features to build powerful integrations:

- **[App Configuration](../guides/app.md)** - Configure middleware, OAuth, and dynamic secret resolution
- **[Webhooks](../guides/webhooks.md)** - Learn about different event types and best practices
- **[Custom Actions](../guides/custom-actions.md)** - Build interactive forms and workflows
- **[Client API](../guides/client-api.md)** - Make authenticated calls to Frame.io's API
- **[Middleware](../guides/middleware.md)** - Add logging, metrics, and error handling
- **[User Authentication](../guides/user-auth.md)** - Enable Adobe Login OAuth for user-specific actions

!!! tip "Building for multiple workspaces?"
    If you're building a product that will be installed across many Frame.io workspaces, the [Self-Service Installation](../guides/self-service-install.md) system handles webhook/action registration and secret management automatically — no manual configuration per workspace.

## Troubleshooting

**"Invalid signature" error**

- Verify secrets in `.env` match those from Frame.io
- Ensure you're using the correct secret for each handler

**Can't see the custom action**

- Refresh the Frame.io page
- Check the action is enabled in workspace settings

**Webhook not triggering**

- Verify ngrok is running and the URL is correct
- Check event types match exactly between Frame.io and your code

For more help, see the [API Reference](../reference/api.md) or check the [Frame.io developer documentation](https://next.developer.frame.io).
