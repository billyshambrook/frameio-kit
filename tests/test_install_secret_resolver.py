"""Tests for the InstallationSecretResolver."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from frameio_kit._encryption import TokenEncryption
from frameio_kit._events import ActionEvent, WebhookEvent
from frameio_kit._exceptions import InstallationNotFoundError
from frameio_kit._install_config import InstallConfig
from frameio_kit._install_manager import InstallationManager
from frameio_kit._install_models import ActionRecord, Installation, WebhookRecord
from frameio_kit._install_secret_resolver import InstallationSecretResolver
from frameio_kit._storage import MemoryStorage

TEST_KEY = TokenEncryption.generate_key()


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
def manager(storage):
    encryption = TokenEncryption(key=TEST_KEY)
    config = InstallConfig(app_name="Test")
    return InstallationManager(storage=storage, encryption=encryption, install_config=config)


@pytest.fixture
def resolver(manager):
    return InstallationSecretResolver(manager)


def _make_webhook_event(account_id: str, workspace_id: str, event_type: str = "file.ready") -> WebhookEvent:
    return WebhookEvent(
        account={"id": account_id},
        project={"id": "proj-1"},
        resource={"id": "res-1", "type": "file"},
        type=event_type,
        user={"id": "user-1"},
        workspace={"id": workspace_id},
        timestamp=1234567890,
    )


def _make_action_event(account_id: str, workspace_id: str, event_type: str = "my_app.transcribe") -> ActionEvent:
    return ActionEvent(
        account_id=account_id,
        action_id="act-1",
        interaction_id="int-1",
        project={"id": "proj-1"},
        resource={"id": "res-1", "type": "file"},
        type=event_type,
        user={"id": "user-1"},
        workspace={"id": workspace_id},
        timestamp=1234567890,
    )


class TestGetWebhookSecret:
    async def test_returns_correct_secret(self, resolver, manager):
        now = datetime.now(tz=timezone.utc)
        installation = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="webhook-secret-123",
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[],
        )
        await manager._store_installation(installation)

        event = _make_webhook_event("acc-1", "ws-1")
        secret = await resolver.get_webhook_secret(event)
        assert secret == "webhook-secret-123"

    async def test_raises_when_no_installation(self, resolver):
        event = _make_webhook_event("acc-missing", "ws-missing")
        with pytest.raises(InstallationNotFoundError):
            await resolver.get_webhook_secret(event)

    async def test_raises_when_no_webhook(self, resolver, manager):
        now = datetime.now(tz=timezone.utc)
        installation = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=None,
            actions=[],
        )
        await manager._store_installation(installation)

        event = _make_webhook_event("acc-1", "ws-1")
        with pytest.raises(InstallationNotFoundError):
            await resolver.get_webhook_secret(event)


class TestGetActionSecret:
    async def test_returns_correct_secret_for_matching_event_type(self, resolver, manager):
        now = datetime.now(tz=timezone.utc)
        installation = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=None,
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="action-secret-123",
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                    url="https://myapp.com",
                ),
                ActionRecord(
                    action_id="act-2",
                    secret="action-secret-456",
                    event_type="my_app.export",
                    name="Export",
                    description="Export files",
                    url="https://myapp.com",
                ),
            ],
        )
        await manager._store_installation(installation)

        event = _make_action_event("acc-1", "ws-1", "my_app.transcribe")
        secret = await resolver.get_action_secret(event)
        assert secret == "action-secret-123"

        event2 = _make_action_event("acc-1", "ws-1", "my_app.export")
        secret2 = await resolver.get_action_secret(event2)
        assert secret2 == "action-secret-456"

    async def test_raises_when_no_installation(self, resolver):
        event = _make_action_event("acc-missing", "ws-missing")
        with pytest.raises(InstallationNotFoundError):
            await resolver.get_action_secret(event)

    async def test_raises_when_no_matching_action(self, resolver, manager):
        now = datetime.now(tz=timezone.utc)
        installation = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=None,
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="s",
                    event_type="my_app.other",
                    name="Other",
                    description="Other action",
                    url="https://myapp.com",
                ),
            ],
        )
        await manager._store_installation(installation)

        event = _make_action_event("acc-1", "ws-1", "my_app.nonexistent")
        with pytest.raises(InstallationNotFoundError):
            await resolver.get_action_secret(event)
