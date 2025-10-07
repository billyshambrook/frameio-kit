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

## Step 2: Your First Application

Let's build a simple application that demonstrates both [Custom Actions](custom_actions.md) and [Webhooks](webhooks.md).

### Step 2a: Create the Application File

Create a file named `main.py` in your project directory:

```python
import os
import uvicorn
from frameio_kit import App, ActionEvent, WebhookEvent, Message

# Initialize the app
app = App()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Step 2b: Add a Custom Action

Custom Actions let users trigger your code by clicking menu items in Frame.io. Learn more about [Custom Actions](custom_actions.md).

Add this code after the `app = App()` line:

```python
# Custom Action: Responds to user clicks
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
```

**What this does:**
- Creates a "Say Hello" menu item in Frame.io
- When clicked, prints the user's name to your console
- Shows a greeting message in the Frame.io UI

### Step 2c: Add a Webhook Handler

Webhooks automatically notify your app when events happen in Frame.io. Learn more about [Webhooks](webhooks.md).

Add this code after the custom action:

```python
# Webhook: Responds to file events
@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")
```

**What this does:**
- Listens for `file.ready` events from Frame.io
- Prints the file ID when a file is processed
- Shows a confirmation message in the Frame.io UI

### Step 2d: Your Complete Application

Your `main.py` should now look like this:

```python
import os
import uvicorn
from frameio_kit import App, ActionEvent, WebhookEvent, Message

# Initialize the app
app = App()

# Custom Action: Responds to user clicks
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

# Webhook: Responds to file events
@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def on_file_ready(event: WebhookEvent):
    print(f"File {event.resource_id} is ready!")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Understanding the Code

- **`App()`** - Creates your Frame.io integration
- **`@app.on_action`** - Decorator for [Custom Actions](custom_actions.md) (user-triggered)
- **`@app.on_webhook`** - Decorator for [Webhooks](webhooks.md) (event-triggered)
- **`Message`** - Response object that displays in Frame.io UI
- **`event.user.name`** - Access to user information from the event
- **`event.resource_id`** - ID of the file or resource that triggered the event

## Step 3: Expose Your Local Server

Frame.io needs a public URL to send events to. For local development, use ngrok:

### Install ngrok
1. Go to [ngrok.com](https://ngrok.com/download) and download ngrok
2. Follow the installation instructions for your platform

### Start a tunnel
```bash
ngrok http 8000
```

You'll see output like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

**Copy the HTTPS URL** - you'll need this for Frame.io configuration.

## Step 4: Configure Frame.io

Now that you have a public URL, configure Frame.io to send events to your app.

### Create a Custom Action

1. **Go to Frame.io** and navigate to your workspace settings
2. **Click "Actions"** in the left sidebar
3. **Click "Create Custom Action"**
4. **Fill in the details**:
   - **Name**: `Say Hello`
   - **Description**: `A simple greeting action`
   - **Event**: `greeting.say_hello`
   - **URL**: Your ngrok URL (e.g., `https://abc123.ngrok-free.app`)
5. **Click "Create"** and **copy the signing secret**

### Create a Webhook

1. **Go to "Webhooks"** in the same settings page
2. **Click "Create Webhook"**
3. **Fill in the details**:
   - **Event Types**: Select `file.ready`
   - **URL**: Your ngrok URL (same as above)
4. **Click "Create"** and **copy the signing secret**

## Step 5: Set Up Environment Variables

Now that you have the secrets from Frame.io, create a `.env` file in your project directory:

```bash
# .env
ACTION_SECRET=your-action-secret-from-frame-io
WEBHOOK_SECRET=your-webhook-secret-from-frame-io
```

Replace the placeholder values with the actual secrets you copied from Frame.io.

## Step 6: Run Your Application

Start your application:

```bash
uvicorn main:app --reload
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

## Step 7: Test Your Integration

### Test the Custom Action
1. **Right-click on any asset** in Frame.io
2. **Look for "Say Hello"** in the context menu
3. **Click it** and you should see a greeting message!

### Test the Webhook
1. **Upload a file** to Frame.io
2. **Wait for it to process** (you'll see "Ready" status)
3. **Check your terminal** - you should see the webhook message!

## What Just Happened?

You've successfully built a Frame.io integration that:

- **Responds to user actions** - Custom actions let users trigger your code
- **Processes file events** - Webhooks notify you when things happen
- **Returns user feedback** - Messages appear in the Frame.io UI
- **Handles authentication** - Secrets ensure only Frame.io can call your app

## Next Steps

Now that you have a working integration, explore these guides:

- **[Webhooks](webhooks.md)** - Learn about different event types and patterns
- **[Custom Actions](custom_actions.md)** - Build interactive forms and workflows  
- **[Client API](client_api.md)** - Make calls back to Frame.io's API
- **[Middleware](middleware.md)** - Add cross-cutting concerns to your integration

## Common Issues

### "No handler registered for event type"
- **Check your event types** match exactly between Frame.io and your code
- **Restart your application** after making changes

### "Invalid signature" error
- **Verify your secrets** are correct in the `.env` file
- **Make sure you're using the right secret** for the right event type

### ngrok connection issues
- **Check ngrok is running** and the URL is correct
- **Try restarting ngrok** if the connection drops

### Can't see the custom action
- **Refresh the Frame.io page** after creating the action
- **Check the action is enabled** in your workspace settings

## Need Help?

- **Check the [API Reference](../api_reference.md)** for detailed documentation

Congratulations! You've built your first Frame.io integration with `frameio-kit`! 🎉

