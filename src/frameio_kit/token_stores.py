"""Built-in TokenStore implementations for frameio-kit.

This module provides ready-to-use TokenStore implementations for common storage
backends. You can use these directly or as reference implementations for your
own custom storage solutions.
"""

import time
from datetime import datetime, timedelta
from typing import Any

from .oauth import TokenStore


class InMemoryTokenStore(TokenStore):
    """In-memory token storage for development and testing.

    This implementation stores tokens in a simple Python dictionary. All tokens
    are lost when the application restarts.

    WARNING: This is NOT suitable for production use. Use a persistent storage
    backend like DynamoDB, PostgreSQL, Redis, etc. for production deployments.

    Example:
        ```python
        from frameio_kit import App
        from frameio_kit.token_stores import InMemoryTokenStore

        app = App(
            oauth_client_id="...",
            oauth_client_secret="...",
            oauth_redirect_uri="...",
            token_store=InMemoryTokenStore()
        )
        ```
    """

    def __init__(self):
        """Initialize the in-memory token store."""
        self._tokens: dict[str, dict[str, Any]] = {}

    async def save_token(self, user_id: str, token_data: dict[str, Any]) -> None:
        """Save token data for a user.

        Automatically adds expiration timestamp based on expires_in value.

        Args:
            user_id: The Frame.io user ID.
            token_data: Dictionary containing access_token, refresh_token,
                expires_in, and token_type.
        """
        # Add expiration timestamp for easier checking
        token_data_with_expiry = token_data.copy()
        if "expires_in" in token_data:
            expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
            token_data_with_expiry["expires_at"] = expires_at.isoformat()

        self._tokens[user_id] = token_data_with_expiry

    async def get_token(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve token data for a user.

        Args:
            user_id: The Frame.io user ID.

        Returns:
            Dictionary containing token data, or None if not found.
        """
        return self._tokens.get(user_id)

    async def delete_token(self, user_id: str) -> None:
        """Delete token data for a user.

        Args:
            user_id: The Frame.io user ID.
        """
        self._tokens.pop(user_id, None)

    def clear_all(self) -> None:
        """Clear all stored tokens. Useful for testing."""
        self._tokens.clear()


class DynamoDBTokenStore(TokenStore):
    """DynamoDB-based token storage for production use.

    This implementation uses AWS DynamoDB for persistent, scalable token storage.
    It automatically handles token expiration timestamps and provides TTL support.

    Prerequisites:
        - Install boto3: `pip install boto3` or `uv add boto3`
        - Configure AWS credentials (environment variables, IAM role, or AWS config)
        - Create a DynamoDB table with the following schema:
            - Partition Key: user_id (String)
            - Optional: Enable TTL on the 'ttl' attribute for automatic cleanup

    Table Schema:
        ```
        Partition Key: user_id (String)
        Attributes:
            - user_id: Frame.io user ID
            - access_token: OAuth access token
            - refresh_token: OAuth refresh token
            - expires_in: Token expiration duration in seconds
            - expires_at: ISO timestamp when token expires
            - token_type: Token type (usually "Bearer")
            - ttl: Unix timestamp for DynamoDB TTL (optional)
            - updated_at: ISO timestamp of last update
        ```

    Example:
        ```python
        from frameio_kit import App
        from frameio_kit.token_stores import DynamoDBTokenStore

        token_store = DynamoDBTokenStore(
            table_name="frameio-user-tokens",
            region_name="us-east-1"
        )

        app = App(
            oauth_client_id="...",
            oauth_client_secret="...",
            oauth_redirect_uri="...",
            token_store=token_store
        )
        ```

    Creating the DynamoDB Table (AWS CLI):
        ```bash
        aws dynamodb create-table \\
            --table-name frameio-user-tokens \\
            --attribute-definitions AttributeName=user_id,AttributeType=S \\
            --key-schema AttributeName=user_id,KeyType=HASH \\
            --billing-mode PAY_PER_REQUEST \\
            --region us-east-1

        # Optional: Enable TTL for automatic token cleanup
        aws dynamodb update-time-to-live \\
            --table-name frameio-user-tokens \\
            --time-to-live-specification "Enabled=true, AttributeName=ttl"
        ```
    """

    def __init__(
        self,
        table_name: str,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        enable_ttl: bool = True,
        ttl_days: int = 90,
    ):
        """Initialize the DynamoDB token store.

        Args:
            table_name: Name of the DynamoDB table.
            region_name: AWS region name (e.g., "us-east-1"). If None, uses default.
            endpoint_url: Custom endpoint URL (useful for local DynamoDB). If None, uses AWS.
            aws_access_key_id: AWS access key ID. If None, uses default credentials.
            aws_secret_access_key: AWS secret access key. If None, uses default credentials.
            enable_ttl: Whether to set TTL attribute for automatic cleanup.
            ttl_days: Number of days before token entry expires (for TTL).

        Raises:
            ImportError: If boto3 is not installed.
        """
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for DynamoDBTokenStore. "
                "Install it with: pip install boto3 or uv add boto3"
            )

        self.table_name = table_name
        self.enable_ttl = enable_ttl
        self.ttl_days = ttl_days

        # Initialize DynamoDB client
        session_kwargs = {}
        if region_name:
            session_kwargs["region_name"] = region_name
        if aws_access_key_id:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self.dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url, **session_kwargs)
        self.table = self.dynamodb.Table(table_name)

    async def save_token(self, user_id: str, token_data: dict[str, Any]) -> None:
        """Save token data for a user in DynamoDB.

        Args:
            user_id: The Frame.io user ID.
            token_data: Dictionary containing access_token, refresh_token,
                expires_in, and token_type.
        """
        # Prepare item for DynamoDB
        item = {
            "user_id": user_id,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "token_type": token_data.get("token_type", "Bearer"),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Add expiration timestamp
        if "expires_in" in token_data:
            expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
            item["expires_at"] = expires_at.isoformat()

            # Add TTL for automatic cleanup (optional)
            if self.enable_ttl:
                ttl_timestamp = int(time.time()) + (self.ttl_days * 24 * 60 * 60)
                item["ttl"] = ttl_timestamp

        # Store in DynamoDB
        self.table.put_item(Item=item)

    async def get_token(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve token data for a user from DynamoDB.

        Args:
            user_id: The Frame.io user ID.

        Returns:
            Dictionary containing token data, or None if not found.
        """
        response = self.table.get_item(Key={"user_id": user_id})

        if "Item" not in response:
            return None

        item = response["Item"]

        # Convert DynamoDB item to token data dict
        token_data = {
            "access_token": item.get("access_token"),
            "refresh_token": item.get("refresh_token"),
            "expires_in": item.get("expires_in"),
            "token_type": item.get("token_type", "Bearer"),
        }

        # Include expiration timestamp if available
        if "expires_at" in item:
            token_data["expires_at"] = item["expires_at"]

        return token_data

    async def delete_token(self, user_id: str) -> None:
        """Delete token data for a user from DynamoDB.

        Args:
            user_id: The Frame.io user ID.
        """
        self.table.delete_item(Key={"user_id": user_id})

    def is_token_expired(self, token_data: dict[str, Any]) -> bool:
        """Check if a token has expired.

        Args:
            token_data: Dictionary containing token data with expires_at field.

        Returns:
            True if the token is expired, False otherwise.
        """
        if "expires_at" not in token_data:
            return False

        expires_at = datetime.fromisoformat(token_data["expires_at"])
        # Add a 5-minute buffer to refresh before actual expiration
        return datetime.utcnow() >= (expires_at - timedelta(minutes=5))
