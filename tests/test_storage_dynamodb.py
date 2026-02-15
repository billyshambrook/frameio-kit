"""Unit tests for DynamoDBStorage auto-create table behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from frameio_kit._storage_dynamodb import DynamoDBStorage


def _make_client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": ""}}, "CreateTable")


@pytest.fixture
def mock_session():
    with patch("aioboto3.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        yield session


def _setup_dynamodb_resource(mock_session):
    """Set up mock DynamoDB resource for get/put/delete operations."""
    table = AsyncMock()
    table.get_item.return_value = {}
    resource = AsyncMock()
    resource.Table.return_value = table
    mock_session.resource.return_value.__aenter__.return_value = resource
    return table


def _setup_dynamodb_client(mock_session, *, create_side_effect=None):
    """Set up mock DynamoDB client for create_table operations."""
    waiter = AsyncMock()
    client = AsyncMock()
    # get_waiter is a sync method that returns a waiter object
    client.get_waiter = MagicMock(return_value=waiter)
    if create_side_effect:
        client.create_table.side_effect = create_side_effect
    mock_session.client.return_value.__aenter__.return_value = client
    return client, waiter


class TestCreateTableFalse:
    async def test_create_table_false_does_not_create(self, mock_session):
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table")

        await storage.get("key")

        mock_session.client.assert_not_called()

    async def test_default_is_false(self, mock_session):
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table")

        await storage.put("key", {"data": "value"})

        mock_session.client.assert_not_called()


class TestCreateTableTrue:
    async def test_create_table_creates_on_first_put(self, mock_session):
        client, waiter = _setup_dynamodb_client(mock_session)
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.put("key", {"data": "value"})

        client.create_table.assert_called_once_with(
            TableName="test-table",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

    async def test_create_table_enables_ttl(self, mock_session):
        client, waiter = _setup_dynamodb_client(mock_session)
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.put("key", {"data": "value"})

        client.update_time_to_live.assert_called_once_with(
            TableName="test-table",
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "ttl",
            },
        )

    async def test_create_table_waits_for_active(self, mock_session):
        client, waiter = _setup_dynamodb_client(mock_session)
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.put("key", {"data": "value"})

        client.get_waiter.assert_called_once_with("table_exists")
        waiter.wait.assert_called_once_with(TableName="test-table")

    async def test_create_table_skips_if_exists(self, mock_session):
        client, waiter = _setup_dynamodb_client(
            mock_session,
            create_side_effect=_make_client_error("ResourceInUseException"),
        )
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.put("key", {"data": "value"})

        client.create_table.assert_called_once()
        waiter.wait.assert_called_once()
        client.update_time_to_live.assert_not_called()

    async def test_create_table_only_once(self, mock_session):
        client, waiter = _setup_dynamodb_client(mock_session)
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.put("k1", {"a": "1"})
        await storage.put("k2", {"b": "2"})

        client.create_table.assert_called_once()

    async def test_create_table_on_get(self, mock_session):
        client, waiter = _setup_dynamodb_client(mock_session)
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.get("key")

        client.create_table.assert_called_once()

    async def test_create_table_on_delete(self, mock_session):
        client, waiter = _setup_dynamodb_client(mock_session)
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        await storage.delete("key")

        client.create_table.assert_called_once()

    async def test_create_table_propagates_other_errors(self, mock_session):
        client, waiter = _setup_dynamodb_client(
            mock_session,
            create_side_effect=_make_client_error("AccessDeniedException"),
        )
        _setup_dynamodb_resource(mock_session)
        storage = DynamoDBStorage(table_name="test-table", create_table=True)

        with pytest.raises(ClientError) as exc_info:
            await storage.put("key", {"data": "value"})

        assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"
