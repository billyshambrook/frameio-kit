# frameio-kit: Build Powerful Frame.io Integrations in Minutes

**frameio-kit** is the fastest way to build robust, scalable integrations with Frame.io. Stop wrestling with webhook signatures, API authentication, and event parsing – focus on what makes your integration unique.

## 🚀 Get Started in 5 Minutes

Ready to build your first Frame.io integration? Our [Getting Started guide](usage/getting_started.md) will have you up and running with both webhooks and custom actions in just a few minutes.

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

## ⚡ Why frameio-kit?

- **Decorator-based routing** - `@app.on_webhook` and `@app.on_action` make event handling trivial
- **Automatic validation** - Pydantic models give you full type safety and editor support
- **Modern Python** - Built for Python 3.13+ with full type hints
- **Secure by default** - Built-in signature verification for all requests
- **Error handling** - Graceful failure handling and retry logic

## 🎯 What Can You Build?

### **Automated Workflows**
- **File processing pipelines** - Automatically process videos, images, and documents
- **Content moderation** - Scan and approve content before publication
- **Asset management** - Organize, tag, and categorize your media library

### **Interactive Tools**
- **Custom actions** - Build right-click menu items that do exactly what you need
- **User forms** - Collect input with interactive forms in the Frame.io UI
- **Real-time notifications** - Keep teams updated with instant alerts

### **API Integrations**
- **Third-party services** - Connect Frame.io to your favorite tools
- **Data synchronization** - Keep external systems in sync with Frame.io
- **Custom dashboards** - Build analytics and reporting tools

## 📚 Learn More

### **Core Concepts**
- **[Webhooks](usage/webhooks.md)** - React to Frame.io events automatically
- **[Custom Actions](usage/custom_actions.md)** - Build interactive user experiences
- **[Client API](usage/client_api.md)** - Make calls back to Frame.io's API
- **[Middleware](usage/middleware.md)** - Add cross-cutting concerns to your integration
- **[User Authentication](usage/user_auth.md)** - Enable Adobe Login OAuth for user-specific actions

### **Advanced Features**
- **[API Reference](api_reference.md)** - Complete documentation for all classes and methods
- **Type safety** - Full Pydantic models for all event types
- **Async patterns** - Best practices for high-performance integrations

## 🛠️ Quick Examples

### **File Processing Pipeline**
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

### **Interactive Custom Action**
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

## 🎉 Ready to Build?

1. **Start with our [Getting Started guide](usage/getting_started.md)** - Get up and running in minutes
2. **Explore the [Usage Guides](usage/webhooks.md)** - Learn about webhooks, actions, and more
3. **Check out the [API reference](api_reference.md)** - Complete documentation
4. **Build something amazing** - The only limit is your imagination!

---

**frameio-kit** - Because building Frame.io integrations should be fun, not frustrating. 🚀
