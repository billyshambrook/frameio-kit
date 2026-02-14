"""Tests for the InstallationManager."""

from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frameio_kit._encryption import TokenEncryption
from frameio_kit._install_manager import InstallationManager, validate_uuid
from frameio_kit._install_models import (
    ActionManifestEntry,
    ActionRecord,
    HandlerManifest,
    Installation,
    WebhookRecord,
)
from frameio_kit._storage import MemoryStorage

TEST_KEY = TokenEncryption.generate_key()


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
def encryption():
    return TokenEncryption(key=TEST_KEY)


@pytest.fixture
def manager(storage, encryption):
    return InstallationManager(
        storage=storage,
        encryption=encryption,
        app_name="Test App",
    )


@dataclass
class FakeHandlerRegistration:
    name: str | None = None
    description: str | None = None


class TestBuildManifest:
    def test_webhooks_only(self, manager):
        manifest = manager.build_manifest(
            webhook_handlers={"file.ready": object(), "comment.created": object()},
            action_handlers={},
        )
        assert manifest.webhook_events == ["comment.created", "file.ready"]
        assert manifest.actions == []

    def test_actions_only(self, manager):
        manifest = manager.build_manifest(
            webhook_handlers={},
            action_handlers={
                "my_app.transcribe": FakeHandlerRegistration(name="Transcribe", description="Transcribe audio"),
            },
        )
        assert manifest.webhook_events == []
        assert len(manifest.actions) == 1
        assert manifest.actions[0].event_type == "my_app.transcribe"
        assert manifest.actions[0].name == "Transcribe"

    def test_both(self, manager):
        manifest = manager.build_manifest(
            webhook_handlers={"file.ready": object()},
            action_handlers={
                "my_app.export": FakeHandlerRegistration(name="Export", description="Export files"),
            },
        )
        assert len(manifest.webhook_events) == 1
        assert len(manifest.actions) == 1

    def test_empty(self, manager):
        manifest = manager.build_manifest(webhook_handlers={}, action_handlers={})
        assert manifest.webhook_events == []
        assert manifest.actions == []


class TestGetInstallation:
    async def test_returns_none_when_not_found(self, manager):
        result = await manager.get_installation("acc-1", "ws-1")
        assert result is None

    async def test_returns_installation_with_decrypted_secrets(self, manager, storage):
        now = datetime.now(tz=timezone.utc)
        webhook_secret = "webhook-secret-123"
        action_secret = "action-secret-456"

        installation = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret=webhook_secret,
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret=action_secret,
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                    url="https://myapp.com",
                ),
            ],
        )

        # Store with encrypted secrets (mimicking _store_installation)
        await manager._store_installation(installation)

        # Retrieve and verify decryption
        result = await manager.get_installation("acc-1", "ws-1")
        assert result is not None
        assert result.webhook is not None
        assert result.webhook.secret == webhook_secret
        assert len(result.actions) == 1
        assert result.actions[0].secret == action_secret


class TestInstall:
    async def test_creates_webhook_and_actions(self, manager):
        manifest = HandlerManifest(
            webhook_events=["file.ready", "comment.created"],
            actions=[
                ActionManifestEntry(event_type="my_app.transcribe", name="Transcribe", description="Transcribe audio"),
            ],
        )

        # Mock the Client
        mock_webhook_response = MagicMock()
        mock_webhook_response.data.id = "wh-new-1"
        mock_webhook_response.data.secret = "wh-secret-new"

        mock_action_response = MagicMock()
        mock_action_response.data.id = "act-new-1"
        mock_action_response.data.secret = "act-secret-new"

        with (
            patch("frameio_kit._install_manager.Client") as MockClient,
        ):
            mock_client = AsyncMock()
            mock_client.webhooks.create = AsyncMock(return_value=mock_webhook_response)
            mock_client.experimental.custom_actions.actions_create = AsyncMock(return_value=mock_action_response)
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await manager.install(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                user_id="user-1",
                base_url="https://myapp.com",
                manifest=manifest,
            )

        assert result.account_id == "acc-1"
        assert result.workspace_id == "ws-1"
        assert result.webhook is not None
        assert result.webhook.webhook_id == "wh-new-1"
        assert result.webhook.secret == "wh-secret-new"
        assert result.webhook.events == ["file.ready", "comment.created"]
        assert len(result.actions) == 1
        assert result.actions[0].action_id == "act-new-1"
        assert result.actions[0].secret == "act-secret-new"

        # Verify stored in storage (encrypted)
        stored = await manager.get_installation("acc-1", "ws-1")
        assert stored is not None
        assert stored.webhook is not None
        assert stored.webhook.secret == "wh-secret-new"

    async def test_install_no_webhooks(self, manager):
        manifest = HandlerManifest(
            webhook_events=[],
            actions=[
                ActionManifestEntry(event_type="my_app.export", name="Export", description="Export files"),
            ],
        )

        mock_action_response = MagicMock()
        mock_action_response.data.id = "act-1"
        mock_action_response.data.secret = "act-secret"

        with patch("frameio_kit._install_manager.Client") as MockClient:
            mock_client = AsyncMock()
            mock_client.experimental.custom_actions.actions_create = AsyncMock(return_value=mock_action_response)
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await manager.install(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                user_id="user-1",
                base_url="https://myapp.com",
                manifest=manifest,
            )

        assert result.webhook is None
        assert len(result.actions) == 1


class TestUpdate:
    async def test_update_adds_new_webhook_events(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="wh-secret",
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[],
        )
        await manager._store_installation(existing)

        manifest = HandlerManifest(
            webhook_events=["file.ready", "comment.created"],
            actions=[],
        )

        with patch("frameio_kit._install_manager.Client") as MockClient:
            mock_client = AsyncMock()
            mock_client.webhooks.update = AsyncMock(return_value=MagicMock())
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await manager.update(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                base_url="https://myapp.com",
                manifest=manifest,
                existing=existing,
            )

        assert result.webhook is not None
        assert set(result.webhook.events) == {"file.ready", "comment.created"}
        # Secret preserved from existing
        assert result.webhook.secret == "wh-secret"
        mock_client.webhooks.update.assert_called_once()

    async def test_update_adds_new_action(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=None,
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="act-secret-1",
                    event_type="my_app.export",
                    name="Export",
                    description="Export files",
                    url="https://myapp.com",
                ),
            ],
        )
        await manager._store_installation(existing)

        manifest = HandlerManifest(
            webhook_events=[],
            actions=[
                ActionManifestEntry(event_type="my_app.export", name="Export", description="Export files"),
                ActionManifestEntry(event_type="my_app.transcribe", name="Transcribe", description="Transcribe audio"),
            ],
        )

        mock_action_response = MagicMock()
        mock_action_response.data.id = "act-new"
        mock_action_response.data.secret = "act-secret-new"

        with patch("frameio_kit._install_manager.Client") as MockClient:
            mock_client = AsyncMock()
            mock_client.experimental.custom_actions.actions_create = AsyncMock(return_value=mock_action_response)
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await manager.update(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                base_url="https://myapp.com",
                manifest=manifest,
                existing=existing,
            )

        assert len(result.actions) == 2
        # Original preserved
        assert any(a.action_id == "act-1" and a.secret == "act-secret-1" for a in result.actions)
        # New one created
        assert any(a.action_id == "act-new" and a.secret == "act-secret-new" for a in result.actions)

    async def test_update_removes_stale_action(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=None,
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="act-secret-1",
                    event_type="my_app.old",
                    name="Old",
                    description="Old action",
                    url="https://myapp.com",
                ),
            ],
        )
        await manager._store_installation(existing)

        manifest = HandlerManifest(webhook_events=[], actions=[])

        with patch("frameio_kit._install_manager.Client") as MockClient:
            mock_client = AsyncMock()
            mock_client.experimental.custom_actions.actions_delete = AsyncMock()
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await manager.update(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                base_url="https://myapp.com",
                manifest=manifest,
                existing=existing,
            )

        assert len(result.actions) == 0
        mock_client.experimental.custom_actions.actions_delete.assert_called_once_with("acc-1", "act-1")

    async def test_update_patches_modified_action(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=None,
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="act-secret-1",
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Old description",
                    url="https://myapp.com",
                ),
            ],
        )
        await manager._store_installation(existing)

        manifest = HandlerManifest(
            webhook_events=[],
            actions=[
                ActionManifestEntry(
                    event_type="my_app.transcribe",
                    name="Transcribe V2",
                    description="New description",
                ),
            ],
        )

        with patch("frameio_kit._install_manager.Client") as MockClient:
            mock_client = AsyncMock()
            mock_client.experimental.custom_actions.actions_update = AsyncMock(return_value=MagicMock())
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await manager.update(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                base_url="https://myapp.com",
                manifest=manifest,
                existing=existing,
            )

        assert len(result.actions) == 1
        assert result.actions[0].name == "Transcribe V2"
        assert result.actions[0].description == "New description"
        # Secret preserved
        assert result.actions[0].secret == "act-secret-1"
        mock_client.experimental.custom_actions.actions_update.assert_called_once()


class TestUninstall:
    async def test_deletes_webhook_and_actions(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="wh-secret",
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="act-secret",
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                    url="https://myapp.com",
                ),
            ],
        )
        await manager._store_installation(existing)

        with patch("frameio_kit._install_manager.Client") as MockClient:
            mock_client = AsyncMock()
            mock_client.webhooks.delete = AsyncMock()
            mock_client.experimental.custom_actions.actions_delete = AsyncMock()
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            await manager.uninstall(
                token="test-token",
                account_id="acc-1",
                workspace_id="ws-1",
                existing=existing,
            )

        mock_client.webhooks.delete.assert_called_once_with("acc-1", "wh-1")
        mock_client.experimental.custom_actions.actions_delete.assert_called_once_with("acc-1", "act-1")

        # Verify removed from storage
        result = await manager.get_installation("acc-1", "ws-1")
        assert result is None


class TestNeedsUpdate:
    def test_no_changes(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="s",
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="s",
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                    url="https://myapp.com",
                ),
            ],
        )
        manifest = HandlerManifest(
            webhook_events=["file.ready"],
            actions=[
                ActionManifestEntry(event_type="my_app.transcribe", name="Transcribe", description="Transcribe audio"),
            ],
        )
        assert manager.needs_update(manifest, existing) is False

    def test_new_webhook_event(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="s",
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[],
        )
        manifest = HandlerManifest(
            webhook_events=["file.ready", "comment.created"],
            actions=[],
        )
        assert manager.needs_update(manifest, existing) is True


class TestComputeDiff:
    def test_diff_with_all_change_types(self, manager):
        now = datetime.now(tz=timezone.utc)
        existing = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="s",
                events=["file.ready", "comment.created"],
                url="https://myapp.com",
            ),
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="s1",
                    event_type="my_app.old",
                    name="Old Action",
                    description="Remove me",
                    url="https://myapp.com",
                ),
                ActionRecord(
                    action_id="act-2",
                    secret="s2",
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Old desc",
                    url="https://myapp.com",
                ),
            ],
        )
        manifest = HandlerManifest(
            webhook_events=["file.ready", "file.versioned"],
            actions=[
                ActionManifestEntry(event_type="my_app.transcribe", name="Transcribe", description="New desc"),
                ActionManifestEntry(event_type="my_app.new", name="New Action", description="Added"),
            ],
        )

        diff = manager.compute_diff(manifest, existing)

        assert diff.webhook_events_added == ["file.versioned"]
        assert diff.webhook_events_removed == ["comment.created"]
        assert len(diff.actions_added) == 1
        assert diff.actions_added[0].event_type == "my_app.new"
        assert len(diff.actions_removed) == 1
        assert diff.actions_removed[0].event_type == "my_app.old"
        assert len(diff.actions_modified) == 1
        assert diff.actions_modified[0].event_type == "my_app.transcribe"
        assert diff.has_changes is True


class TestValidateUuid:
    def test_valid_uuid(self):
        result = validate_uuid("12345678-1234-1234-1234-123456789abc", "test")
        assert result == "12345678-1234-1234-1234-123456789abc"

    def test_invalid_uuid(self):
        with pytest.raises(ValueError, match="Invalid test"):
            validate_uuid("not-a-uuid", "test")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Invalid test"):
            validate_uuid("", "test")


class TestEncryptDecryptSecrets:
    def test_round_trip(self, manager):
        original = "my-super-secret"
        encrypted = manager._encrypt_secret(original)
        assert encrypted != original
        decrypted = manager._decrypt_secret(encrypted)
        assert decrypted == original
