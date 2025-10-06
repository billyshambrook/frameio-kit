# Getting Started

This guide will walk you through the basic setup and a simple "Hello, World!" example to get you started with `frameio-kit`.

## Installation

We recommend using [uv](https://docs.astral.sh/uv/) for project and dependency management. To add `frameio-kit` to your project, run:

```bash
uv add frameio-kit
```

Alternatively, you can install it directly with pip:

```bash
pip install frameio-kit
```

## Your First Application

Create a file named `main.py` and add the following code. This simple application will respond to a custom action with a greeting message.

```python

import os
import uvicorn
from frameio_kit import App, ActionEvent, Message

# It's recommended to load secrets from environment variables
# For local development, you can use a .env file
# ACTION_SECRET="your-super-secret-string"
app = App()

@app.on_action(
    event_type="greeting.say_hello",
    name="Say Hello",
    description="A simple greeting action.",
    secret=os.environ["ACTION_SECRET"]
)
async def on_greeting(event: ActionEvent):
    """
    This handler is triggered when a user clicks the 'Say Hello'
    custom action in the Frame.io UI.
    """
    print(f"Action triggered by user: {event.user.id}")
    return Message(
        title="Greetings!",
        description=f"Hello from your first frameio-kit application!"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Running the App

To run your application, use an ASGI server like uvicorn:

```bash
uvicorn main:app --reload
```

## Exposing Your Endpoint

Frame.io needs a public URL to send events to. For local development, a tunneling service like ngrok is essential.

1. Install ngrok: Follow the instructions on the [ngrok website](https://ngrok.com/download).

2. Start a tunnel:

```bash
ngrok http 8000
```

3. Get your public URL: ngrok will provide a public HTTPS URL (e.g., https://<unique-id>.ngrok-free.app).

## Configuring the Custom Action in Frame.io

1. Navigate to your Workspace settings in Frame.io.

2. Go to the "Actions" tab and create a new Custom Action.

3. Fill in the details:

- Name: `Say Hello`

- Description: `A simple greeting action.`

- Event: `greeting.say_hello` (must match event_type in your code)

- URL: Your public ngrok URL.

4. A Signing Secret will be generated. Copy this and set it as the ACTION_SECRET environment variable for your application.

Now, right-click on an asset in Frame.io, find your "Say Hello" action in the menu, and trigger it. You should see a "Greetings!" message appear in the UI.

