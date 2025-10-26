# frameio-kit

Build robust, scalable Frame.io integrations in minutes. Stop wrestling with webhook signatures, API authentication, and event parsing – focus on what makes your integration unique.

## Quick Start

New to frameio-kit? **[Start with the Getting Started guide →](usage/getting_started.md)**

You'll be up and running with webhooks and custom actions in under 5 minutes.

```python
from frameio_kit import App, WebhookEvent, ActionEvent, Message

app = App()

@app.on_webhook("file.ready", secret="your-secret")
async def on_file_ready(event: WebhookEvent):
    print(f"File is ready!")

@app.on_action("my_app.analyze", "Analyze File", "Analyze this file", "your-secret")
async def analyze_file(event: ActionEvent):
    return Message(title="Analysis Complete", description="File analyzed successfully!")
```

## Why Choose frameio-kit?

- **Simple** - Decorator-based routing makes event handling trivial
- **Type-safe** - Full Pydantic models and IDE autocomplete
- **Async-first** - Handle thousands of concurrent events efficiently
- **Secure** - Automatic signature verification for all requests
- **Batteries included** - Forms, middleware, OAuth, and API client built-in

## What Can You Build?

**Automated Workflows**

- File processing pipelines that handle videos, images, and documents automatically
- Content moderation systems that scan and approve assets before publication
- Asset management tools that organize, tag, and categorize media libraries

**Interactive Tools**

- Custom actions that appear as right-click menu items in Frame.io
- User forms that collect input directly in the Frame.io UI
- Real-time notifications that keep teams updated

**API Integrations**

- Connections to third-party services and tools
- Data synchronization between Frame.io and external systems
- Custom dashboards for analytics and reporting

## Core Concepts

Learn the fundamentals of building Frame.io integrations:

- **[Webhooks](usage/webhooks.md)** - Automatically react to Frame.io events like file uploads and comments
- **[Custom Actions](usage/custom_actions.md)** - Build interactive workflows triggered by user clicks
- **[Client API](usage/client_api.md)** - Make authenticated calls to Frame.io's REST API
- **[Middleware](usage/middleware.md)** - Add logging, metrics, and error handling across all requests
- **[User Authentication](usage/user_auth.md)** - Enable Adobe Login OAuth for user-specific actions

## Advanced Topics

- **[API Reference](api_reference.md)** - Complete documentation for all classes and methods

## Examples

### File Processing Pipeline
```python
@app.on_webhook("file.ready", secret=os.environ["WEBHOOK_SECRET"])
async def process_file(event: WebhookEvent):
    # Get file details
    file = await app.client.files.get(event.resource_id)
    
    # Process the file
    result = await my_processing_service.process(file)
    
    # Add a comment back to Frame.io
    await app.client.comments.create(
        account_id=event.account_id,
        file_id=event.resource_id,
        data={"text": f"Processing complete! Result: {result}"}
    )
```

### Interactive Custom Action
```python
@app.on_action("asset.publish", "Publish Asset", "Publish to social media", os.environ["ACTION_SECRET"])
async def publish_asset(event: ActionEvent):
    if event.data:
        # Form was submitted
        platform = event.data.get("platform")
        caption = event.data.get("caption")
        
        # Publish the asset
        await publish_to_social_media(event.resource_id, platform, caption)
        
        return Message(title="Published!", description=f"Posted to {platform}")
    
    # Show the form
    return Form(
        title="Publish to Social Media",
        fields=[
            SelectField(label="Platform", name="platform", options=PLATFORMS),
            TextField(label="Caption", name="caption", placeholder="Enter your caption...")
        ]
    )
```

## Next Steps

1. **[Getting Started](usage/getting_started.md)** - Build your first integration
2. **[Core Concepts](#core-concepts)** - Learn webhooks, actions, and the API client
3. **[API Reference](api_reference.md)** - Explore the complete API documentation
