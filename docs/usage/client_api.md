# Using the API Client

To make calls back to the Frame.io API from within your handlers, you need an authenticated API client. You can enable this by providing a Frame.io API token when you initialize your `App`.

## Initialization

It is highly recommended to store your API token securely, for example, in an environment variable.

```python
import os
from frameio_kit import App

# The token is loaded from an environment variable named FRAMEIO_TOKEN
app = App(token=os.getenv("FRAMEIO_TOKEN"))
```
Once initialized, the authenticated client is available at `app.client`.

## Making API Calls

The client is an instance of `frameio.AsyncFrameio` from the official `frameio-python-sdk`, so you can use all of its methods and features. The client is organized by API resources, making it intuitive to use.

- **Stable API**: Access methods directly via `app.client`, e.g., `app.client.files.get(...)`. See [frameio](https://pypi.org/project/frameio/) for more information.
- **Experimental API**: Access experimental endpoints via `app.client.experimental`, e.g., `app.client.experimental.actions.list(...)`. See [frameio-experimental](https://pypi.org/project/frameio-experimental/) for more information.

### Example: Add a Comment to a File

This example demonstrates how to use the client within a webhook handler to post a comment back to the file that triggered the event.

```python
import os
from frameio_kit import App, WebhookEvent
from frameio import CreateCommentParamsData

app = App(token=os.getenv("FRAMEIO_TOKEN"))

@app.on_webhook(event_type="file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def add_processing_comment(event: WebhookEvent):
    """
    When a file is ready, this handler adds a comment to it using the API client.
    """
    try:
        comment_text = f"This file has been successfully processed by our automation."
        response = await app.client.comments.create(
            account_id=event.account_id,
            file_id=event.resource_id,
            data=CreateCommentParamsData(text=comment_text),
        )
        print(f"Successfully added comment with ID: {response.data.id}")
    except Exception as e:
        print(f"Failed to add comment: {e}")
```


The `app.client` is fully asynchronous, so remember to use `await` when calling its methods.

