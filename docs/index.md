# frameio-kit: The Python Framework for Building Frame.io Apps

**frameio-kit** is a modern, asynchronous Python framework designed to streamline the development of robust and scalable integrations with Frame.io. It abstracts away the complexities of handling webhooks, securing custom actions, and making authenticated API calls, letting you concentrate on the core logic of your application.

## Key Features

- **Asynchronous First**: Built on modern async/await syntax, frameio-kit is designed for high-performance, non-blocking I/O operations, perfect for handling concurrent webhook deliveries.
- **Simple Decorator-Based Routing**: Use intuitive decorators like `@app.on_webhook` and `@app.on_action` to register functions that respond to Frame.io events.
- **Pydantic Data Validation**: Incoming event payloads are automatically parsed and validated into fully-typed Pydantic models, providing excellent editor support and reducing runtime errors.
- **Secure by Default**: Includes built-in signature verification for all incoming requests, ensuring that your application only processes authentic payloads from Frame.io.
- **Interactive Custom Actions**: Easily build multi-step custom actions with interactive forms. Return a Form object to collect user input and a Message object to display feedback, all without manual JSON construction.
- **Integrated API Client**: An authenticated, asynchronous HTTP client is available out-of-the-box, making it simple to interact with the Frame.io REST API from within your event handlers.
