# Getting Started

Welcome to `frameio-kit`! This guide will take you from zero to a working Frame.io integration in just a few minutes.

## What You'll Build

By the end of this guide, you'll have:

- ✅ A running Frame.io integration
- ✅ A custom action that responds to user clicks
- ✅ A webhook that processes file events
- ✅ An understanding of the core concepts

## Prerequisites

Before you start, make sure you have:

- **Python 3.13+** installed
- **A Frame.io account** with workspace access
- **Basic Python knowledge** (async/await helpful but not required)

## Step 1: Installation

Create a new project directory and install `frameio-kit`:

```bash
# Create project directory
mkdir my-frameio-app
cd my-frameio-app

# Install frameio-kit (we recommend uv for fast, reliable installs)
uv add frameio-kit uvicorn

# Or with pip
pip install frameio-kit uvicorn
```

## Step 2: Create Your Application

Create a file named `main.py` with the following code:

```python
import os
import uvicorn
from frameio_kit import App, ActionEvent, WebhookEvent, Message

app = App()

# Custom Action: Responds to user clicks in Frame.io
@app.on_action(
    event_type="greeting.say_hello",
    name="Say Hello",
    description="A simple greeting action",
    secret=os.environ["ACTION_SECRET"]
)
async def on_greeting(event: ActionEvent):
    print(f"Hello from {event.user.name}!")
    return Message(
        title="Greetings!",
        description="Hello from your first frameio-kit app!"
    )

# Webhook: Responds to file events from Frame.io
@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**What this code does:**

- **Custom Action** - Creates a "Say Hello" menu item in Frame.io that displays a greeting when clicked
- **Webhook** - Listens for `file.ready` events and prints the file ID when files are processed
- **`App()`** - Initializes your Frame.io integration
- **`Message`** - Returns a response that displays in the Frame.io UI

Learn more about [Custom Actions](custom_actions.md) and [Webhooks](webhooks.md).

## Step 3: Expose Your Server

Frame.io needs a public URL to send events to your application. For local development, use [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok-free.app`) – you'll need it for Frame.io configuration.

## Step 4: Configure Frame.io

### Create a Custom Action

1. In Frame.io, navigate to **Workspace Settings → Actions**
2. Click **"Create Custom Action"** and fill in:
   - **Name**: `Say Hello`
   - **Event**: `greeting.say_hello`
   - **URL**: Your ngrok URL
3. Copy the signing secret

### Create a Webhook

1. In the same settings page, go to **Webhooks**
2. Click **"Create Webhook"** and configure:
   - **Event Types**: Select `file.ready`
   - **URL**: Your ngrok URL
3. Copy the signing secret

### Set Environment Variables

Create a `.env` file with the secrets from Frame.io:

```bash
ACTION_SECRET=your-action-secret-here
WEBHOOK_SECRET=your-webhook-secret-here
```

## Step 5: Run Your Application

```bash
uvicorn main:app --reload
```

## Step 6: Test Your Integration

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

- **[Webhooks](webhooks.md)** - Learn about different event types and best practices
- **[Custom Actions](custom_actions.md)** - Build interactive forms and workflows
- **[Client API](client_api.md)** - Make authenticated calls to Frame.io's API
- **[Middleware](middleware.md)** - Add logging, metrics, and error handling
- **[User Authentication](user_auth.md)** - Enable Adobe Login OAuth for user-specific actions

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

For more help, see the [API Reference](../api_reference.md) or check Frame.io's developer documentation.

