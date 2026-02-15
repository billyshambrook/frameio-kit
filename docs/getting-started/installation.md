# Installation

## Prerequisites

Before you start, make sure you have:

- **Python 3.14+** installed
- **A Frame.io account** with workspace access
- **Basic Python knowledge** (async/await helpful but not required)

## Install frameio-kit

Create a new project directory and install frameio-kit:

```bash
# Create project directory
mkdir my-frameio-app
cd my-frameio-app

# Install frameio-kit (we recommend uv for fast, reliable installs)
uv add frameio-kit uvicorn

# Or with pip
pip install frameio-kit uvicorn
```

## Optional Dependencies

frameio-kit provides optional extras for additional features:

| Extra | Command | Description |
|-------|---------|-------------|
| `install` | `pip install frameio-kit[install]` | [Self-service installation system](../guides/self-service-install.md) for workspace onboarding |
| `dynamodb` | `pip install frameio-kit[dynamodb]` | [DynamoDB storage backend](../guides/user-auth.md#multi-server-dynamodbstorage) for multi-server deployments |

You can combine extras: `pip install frameio-kit[install,dynamodb]`

## Frame.io Developer Setup

To receive webhooks and register custom actions, you'll need to configure your app in the Frame.io Developer Console. See the [Frame.io developer documentation](https://next.developer.frame.io) for instructions on creating apps and obtaining credentials.

The [Quickstart](quickstart.md) walks through this step by step.

## Next Steps

- [Quickstart](quickstart.md) — build and run your first integration
- [Concepts](../concepts.md) — understand how Frame.io apps work
