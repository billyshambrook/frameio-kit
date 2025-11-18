# App Configuration

The [`App`](../api_reference.md#frameio_kit.App) class is the central entry point for your Frame.io integration. This guide covers app-level configuration options.

## Basic Initialization

```python
from frameio_kit import App

app = App()
```

## Configuration Options

### API Token

Provide an API token to enable authenticated calls to the Frame.io API via [`app.client`](../api_reference.md#frameio_kit.App.client):

```python
import os

app = App(token=os.getenv("FRAMEIO_TOKEN"))

# Use the client in handlers
@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    file = await app.client.assets.show(
        account_id=event.account_id,
        asset_id=event.resource_id
    )
    print(f"File name: {file.data.name}")
```

See [Client API](client_api.md) for more details.

### Middleware

Add middleware for logging, metrics, error handling, and more:

```python
from frameio_kit import App, Middleware

class LoggingMiddleware(Middleware):
    async def __call__(self, event, next):
        print(f"Processing event: {event.type}")
        response = await next(event)
        print(f"Event processed: {event.type}")
        return response

app = App(middleware=[LoggingMiddleware()])
```

See [Middleware](middleware.md) for detailed examples.

### OAuth Configuration

Enable Adobe Login OAuth for user authentication:

```python
from frameio_kit import App, OAuthConfig

app = App(
    oauth=OAuthConfig(
        client_id=os.getenv("OAUTH_CLIENT_ID"),
        client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
        redirect_uri="https://your-app.com/auth/callback",
        scopes=["openid", "frame.io"],
        base_url="https://your-app.com",
        encryption_key=os.getenv("ENCRYPTION_KEY")
    )
)
```

See [User Authentication](user_auth.md) for complete OAuth setup.

## Dynamic Secret Resolution

When you need to resolve secrets dynamically (e.g., from a database), use the app-level `secret_resolver`.

### SecretResolver Protocol

Implement the [`SecretResolver`](../api_reference.md#frameio_kit.SecretResolver) protocol to provide centralized secret management:

```python
from frameio_kit import App, SecretResolver, WebhookEvent, ActionEvent

class DatabaseSecretResolver:
    """Resolve secrets from a database."""

    def __init__(self, db):
        self.db = db

    async def get_webhook_secret(self, event: WebhookEvent) -> str:
        """Resolve secret for webhook events.

        Args:
            event: The webhook event being processed.

        Returns:
            The secret to use for signature verification.
        """
        # Dynamic lookup based on account
        return await self.db.webhooks.get_secret(event.account_id)

    async def get_action_secret(self, event: ActionEvent) -> str:
        """Resolve secret for action events.

        Args:
            event: The action event being processed.

        Returns:
            The secret to use for signature verification.
        """
        # Dynamic lookup based on resource or action
        return await self.db.actions.get_secret(event.resource.id)

# Initialize app with resolver
resolver = DatabaseSecretResolver(db)
app = App(secret_resolver=resolver)

# Handlers automatically use the app-level resolver
@app.on_webhook("file.ready")
async def on_file_ready(event: WebhookEvent):
    # Secret resolved automatically from database
    pass

@app.on_action("my_app.process", "Process", "Process file")
async def on_process(event: ActionEvent):
    # Secret resolved automatically from database
    pass
```

### When to Use App-Level Resolver

Use the app-level `secret_resolver` when:

- **Multiple tenants**: Different accounts need different secrets
- **Database-backed secrets**: Secrets are stored in your database
- **Centralized management**: All secret resolution logic in one place
- **Dynamic configuration**: Secrets can change without code changes

### Secret Resolution Precedence

The framework follows this precedence order (highest to lowest):

1. **Explicit string secret** at decorator (`secret="..."`)
2. **Decorator-level resolver** function (`secret=my_resolver`)
3. **App-level resolver** (`App(secret_resolver=resolver)`)
4. **Environment variables** (`WEBHOOK_SECRET` / `CUSTOM_ACTION_SECRET`)

This allows you to:

- Use app-level resolver as default for all handlers
- Override with decorator-level resolver for specific handlers
- Override with static secrets for testing or special cases

### Example: Multi-Tenant Application

```python
from frameio_kit import App, SecretResolver, WebhookEvent, ActionEvent
import aioboto3
from botocore.exceptions import ClientError

class MultiTenantSecretResolver:
    """Resolve secrets for different Frame.io accounts (tenants)."""

    def __init__(self, table_name: str = "frameio-secrets"):
        self.table_name = table_name
        self.session = aioboto3.Session()

    async def get_webhook_secret(self, event: WebhookEvent) -> str:
        """Get webhook secret for the account from DynamoDB."""
        async with self.session.resource("dynamodb") as dynamodb:
            table = await dynamodb.Table(self.table_name)
            try:
                response = await table.get_item(
                    Key={
                        "account_id": event.account_id,
                        "config_type": "webhook"
                    }
                )
                if "Item" not in response:
                    raise ValueError(f"No webhook secret found for account {event.account_id}")
                return response["Item"]["secret"]
            except ClientError as e:
                raise ValueError(f"Error fetching webhook secret: {e}")

    async def get_action_secret(self, event: ActionEvent) -> str:
        """Get action secret for the account from DynamoDB."""
        async with self.session.resource("dynamodb") as dynamodb:
            table = await dynamodb.Table(self.table_name)
            try:
                response = await table.get_item(
                    Key={
                        "account_id": event.account_id,
                        "config_type": "action"
                    }
                )
                if "Item" not in response:
                    raise ValueError(f"No action secret found for account {event.account_id}")
                return response["Item"]["secret"]
            except ClientError as e:
                raise ValueError(f"Error fetching action secret: {e}")

# Initialize with DynamoDB table name
app = App(secret_resolver=MultiTenantSecretResolver(table_name="frameio-secrets"))
```

**DynamoDB Table Schema:**

```json
{
  "TableName": "frameio-secrets",
  "KeySchema": [
    { "AttributeName": "account_id", "KeyType": "HASH" },
    { "AttributeName": "config_type", "KeyType": "RANGE" }
  ],
  "AttributeDefinitions": [
    { "AttributeName": "account_id", "AttributeType": "S" },
    { "AttributeName": "config_type", "AttributeType": "S" }
  ]
}
```

**Example Items:**

```json
{
  "account_id": "acc_123",
  "config_type": "webhook",
  "secret": "webhook_secret_for_account_123"
}
{
  "account_id": "acc_123",
  "config_type": "action",
  "secret": "action_secret_for_account_123"
}
```

### Error Handling

When a resolver raises an exception or returns an empty string, the request will fail with HTTP 500:

```python
class SafeSecretResolver:
    """Resolver with proper error handling."""

    async def get_webhook_secret(self, event: WebhookEvent) -> str:
        try:
            secret = await self.db.get_secret(event.account_id)
            if not secret:
                # Log the error
                logger.error(f"No secret for account {event.account_id}")
                # Return a default or raise
                raise ValueError(f"No secret configured for account {event.account_id}")
            return secret
        except Exception as e:
            logger.error(f"Error resolving secret: {e}")
            # Re-raise to trigger 500 response
            raise
```

## Best Practices

1. **Keep secrets secure** - Never log or expose secrets in error messages
2. **Cache when possible** - If secrets don't change often, consider caching
3. **Handle errors gracefully** - Provide clear error messages when secret lookup fails
4. **Test secret resolution** - Ensure resolvers work correctly before deploying
5. **Monitor resolver performance** - Secret lookup happens on every request

## See Also

- [Webhooks](webhooks.md#dynamic-secret-resolution) - Webhook-specific secret resolution
- [Custom Actions](custom_actions.md#dynamic-secret-resolution) - Action-specific secret resolution
- [SecretResolver API Reference](../api_reference.md#frameio_kit.SecretResolver)
