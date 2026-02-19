# How Frame.io Apps Work

This page explains the core concepts behind Frame.io app development and how frameio-kit fits into the picture. If you're already familiar with Frame.io's platform, skip ahead to the [Quickstart](getting-started/quickstart.md).

## What is a Frame.io App?

A Frame.io app is a server-side application that extends Frame.io's functionality. Apps can react to events happening inside Frame.io (like file uploads or comments), add custom menu items to the Frame.io UI, and interact with Frame.io's API to read and write data.

Apps run on your own infrastructure and communicate with Frame.io over HTTPS.

## Key Terms

Before diving in, here are the Frame.io terms used throughout these docs:

- **Account** — a billing entity in Frame.io. Organizations typically have one account. Referenced as `event.account_id` in handlers.
- **Workspace** — a container within an account for organizing projects and teams. A single account can have multiple workspaces. Referenced as `event.workspace_id`.
- **Project** — a collection of files, folders, and review sessions within a workspace.
- **Asset** — any file or folder in Frame.io (videos, images, documents, folders). Also called a "resource" in event payloads — `event.resource_id` (webhooks) or `event.resource_ids` (custom actions) refers to the asset(s) that triggered the event.
- **Event type** — a string like `file.ready` or `comment.created` that identifies what happened. These are defined by Frame.io — see the [full list of event types](https://next.developer.frame.io/platform/docs/guides/webhooks#webhook-event-subscriptions). For custom actions, the event type (e.g., `my_app.analyze`) is a string you define and must match what you configure in Frame.io's developer settings.

## Architecture Overview

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│   Frame.io   │  HTTP   │   Your Server    │  HTTP   │  Frame.io   │
│   Platform   │ ──────► │  (frameio-kit)   │ ──────► │    API      │
│              │ events  │                  │ calls   │             │
└─────────────┘         └──────────────────┘         └─────────────┘
```

1. **Frame.io sends events** to your server when things happen (files uploaded, comments added, users click custom actions)
2. **Your code processes the event** using frameio-kit's handler system
3. **Your code calls the Frame.io API** to read data, create comments, or perform other actions

## Webhooks

Webhooks are automated notifications that Frame.io sends to your server when events occur. They're one-way: Frame.io tells you something happened, and your code decides what to do about it.

Common webhook events include:

- `file.ready` — a file has finished processing and is ready to view
- `comment.created` — someone added a comment
- `project.created` — a new project was created

Your server receives an HTTP POST request with event details (resource IDs, user info, timestamps) and processes it however you need — trigger a pipeline, sync to another system, send a notification.

For the full list of available events, see the [Frame.io webhook documentation](https://next.developer.frame.io/platform/docs/guides/webhooks#webhook-event-subscriptions).

## Custom Actions

Custom actions are interactive menu items that appear in the Frame.io UI. When a user right-clicks on an asset, your custom actions appear alongside Frame.io's built-in options.

The flow works like this:

1. User clicks your action in the Frame.io UI
2. Frame.io sends an HTTP POST to your server
3. Your handler returns either a **Message** (simple feedback) or a **Form** (to collect user input)
4. If you returned a form, the user fills it out and submits — your handler is called again with the form data

This two-step pattern lets you build interactive workflows: ask the user what they want to do, then do it.

For more on custom actions in Frame.io, see the [Frame.io developer documentation](https://next.developer.frame.io/platform/docs/guides/custom-actions).

## Authentication

Frame.io apps use two authentication models depending on the use case:

**Server-to-Server (API Token)** — Your app authenticates with a static API token. All API calls are attributed to the app itself. This is the simplest approach and works for most integrations.

**User Authentication (Adobe OAuth)** — Your app authenticates individual users via Adobe Login. Frame.io is part of Adobe Creative Cloud, so user authentication goes through Adobe's identity platform. API calls are attributed to the specific user, which matters for audit trails and permission enforcement. Use this when you need to act on behalf of specific users.

For details on setting up authentication, see the [Frame.io authentication guide](https://next.developer.frame.io/platform/docs/guides/authentication).

## How frameio-kit Helps

Building a Frame.io app from scratch means handling webhook signature verification, event parsing, ASGI routing, OAuth flows, secret management, and more. frameio-kit handles all of that so you can focus on your business logic:

- **Signature verification** — every incoming request is cryptographically verified
- **Event parsing** — raw HTTP payloads are parsed into typed Python objects with full editor support
- **Decorator-based routing** — `@app.on_webhook` and `@app.on_action` map events to handler functions
- **OAuth flows** — Adobe Login integration with automatic token refresh
- **Secret management** — from environment variables to multi-tenant database-backed resolution
- **Self-service installation** — branded install pages for workspace admins

You write handler functions. frameio-kit handles the rest.

## Single-Tenant vs Multi-Tenant

frameio-kit supports two deployment models:

**Single-tenant** — your app serves one Frame.io workspace. You configure webhook and custom action secrets as environment variables and manage registration manually in the Frame.io developer settings. This is the simplest approach and works well for personal projects and internal company tools. The [Quickstart](getting-started/quickstart.md) builds a single-tenant app.

**Multi-tenant** — your app serves many workspaces across different accounts. The [Self-Service Installation](guides/self-service-install.md) system provides a branded install page where workspace admins can install your app themselves. It automatically creates webhooks and custom actions via the Frame.io API, manages signing secrets per-tenant, and handles updates and uninstalls. This is the model for partners building products that integrate with Frame.io.

## Where to Go Next

- [Installation](getting-started/installation.md) — install frameio-kit and set up prerequisites
- [Quickstart](getting-started/quickstart.md) — build your first integration in minutes
- [Webhooks Guide](guides/webhooks.md) — deep dive into webhook handling
- [Custom Actions Guide](guides/custom-actions.md) — build interactive UI workflows
