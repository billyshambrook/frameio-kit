"""DynamoDB storage backend for token persistence.

This module provides a DynamoDB-backed storage implementation using aioboto3.
Requires the ``aioboto3`` package to be installed separately.

DynamoDB table requirements:
    - Partition key: ``PK`` (String)
    - TTL attribute: ``ttl`` (Number) — enable TTL in DynamoDB for automatic cleanup
"""

import asyncio
import json
import time
from typing import Any

from botocore.exceptions import ClientError


class DynamoDBStorage:
    """DynamoDB storage backend for multi-server deployments.

    Uses aioboto3 (optional dependency) to interact with DynamoDB. Each call
    creates a short-lived resource context manager to avoid holding connections
    open between requests.

    Client-side TTL checking is performed on ``get()`` because DynamoDB's
    built-in TTL cleanup is eventually consistent and may leave expired items
    readable for up to 48 hours.

    Example:
        ```python
        from frameio_kit._storage_dynamodb import DynamoDBStorage

        # Uses boto3 default region resolution
        storage = DynamoDBStorage(table_name="frameio-oauth-tokens")

        # Or specify a region explicitly
        storage = DynamoDBStorage(table_name="frameio-oauth-tokens", region_name="us-east-1")
        ```
    """

    def __init__(
        self,
        table_name: str,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        boto_session_kwargs: dict[str, Any] | None = None,
        create_table: bool = False,
    ) -> None:
        """Initialize DynamoDB storage.

        Args:
            table_name: Name of the DynamoDB table.
            region_name: AWS region (e.g. ``"us-east-1"``). Defaults to the
                boto3 default region from environment variables, AWS config
                files, or instance metadata.
            endpoint_url: Optional endpoint URL (useful for local DynamoDB).
            boto_session_kwargs: Optional extra kwargs passed to ``aioboto3.Session()``.
            create_table: If True, automatically create the table on first use
                if it doesn't already exist. Defaults to False.
        """
        try:
            import aioboto3
        except ImportError:
            raise ImportError(
                "aioboto3 is required for DynamoDBStorage. Install it with: pip install frameio-kit[dynamodb]"
            ) from None

        self._table_name = table_name
        self._region_name = region_name
        self._endpoint_url = endpoint_url
        self._create_table = create_table
        self._table_ensured = False
        self._table_lock = asyncio.Lock()
        self._session = aioboto3.Session(**(boto_session_kwargs or {}))

    def _resource_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self._region_name is not None:
            kwargs["region_name"] = self._region_name
        if self._endpoint_url is not None:
            kwargs["endpoint_url"] = self._endpoint_url
        return kwargs

    async def _ensure_table(self) -> None:
        if self._table_ensured:
            return

        async with self._table_lock:
            if self._table_ensured:
                return

            async with self._session.client("dynamodb", **self._resource_kwargs()) as client:
                try:
                    await client.create_table(
                        TableName=self._table_name,
                        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}],
                        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}],
                        BillingMode="PAY_PER_REQUEST",
                    )
                    waiter = client.get_waiter("table_exists")
                    await waiter.wait(TableName=self._table_name)

                    await client.update_time_to_live(
                        TableName=self._table_name,
                        TimeToLiveSpecification={
                            "Enabled": True,
                            "AttributeName": "ttl",
                        },
                    )
                except ClientError as e:
                    if e.response["Error"]["Code"] != "ResourceInUseException":
                        raise

            self._table_ensured = True

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._create_table:
            await self._ensure_table()
        async with self._session.resource("dynamodb", **self._resource_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            response = await table.get_item(Key={"PK": key})

        item = response.get("Item")
        if item is None:
            return None

        # Client-side TTL check
        ttl = item.get("ttl")
        if ttl is not None and time.time() >= float(ttl):
            await self.delete(key)
            return None

        return json.loads(item["value"])

    async def put(self, key: str, value: dict[str, Any], *, ttl: int | None = None) -> None:
        if self._create_table:
            await self._ensure_table()
        item: dict[str, Any] = {
            "PK": key,
            "value": json.dumps(value),
        }
        if ttl is not None:
            item["ttl"] = int(time.time() + ttl)

        async with self._session.resource("dynamodb", **self._resource_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            await table.put_item(Item=item)

    async def delete(self, key: str) -> None:
        if self._create_table:
            await self._ensure_table()
        async with self._session.resource("dynamodb", **self._resource_kwargs()) as dynamodb:
            table = await dynamodb.Table(self._table_name)
            await table.delete_item(Key={"PK": key})
