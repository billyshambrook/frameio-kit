"""Tests for installation data models."""

from datetime import datetime, timezone

from frameio_kit._install_models import (
    ActionManifestEntry,
    ActionRecord,
    HandlerManifest,
    Installation,
    InstallationDiff,
    WebhookRecord,
)


class TestWebhookRecord:
    def test_serialization(self):
        record = WebhookRecord(
            webhook_id="wh-123",
            secret="secret-abc",
            events=["file.ready", "comment.created"],
            url="https://myapp.com",
        )
        data = record.model_dump()
        assert data["webhook_id"] == "wh-123"
        assert data["events"] == ["file.ready", "comment.created"]

        restored = WebhookRecord.model_validate(data)
        assert restored == record

    def test_json_round_trip(self):
        record = WebhookRecord(
            webhook_id="wh-123",
            secret="secret-abc",
            events=["file.ready"],
            url="https://myapp.com",
        )
        json_str = record.model_dump_json()
        restored = WebhookRecord.model_validate_json(json_str)
        assert restored == record


class TestActionRecord:
    def test_serialization(self):
        record = ActionRecord(
            action_id="act-456",
            secret="secret-xyz",
            event_type="my_app.transcribe",
            name="Transcribe",
            description="Transcribe video audio",
            url="https://myapp.com",
        )
        data = record.model_dump()
        assert data["action_id"] == "act-456"
        assert data["event_type"] == "my_app.transcribe"

        restored = ActionRecord.model_validate(data)
        assert restored == record


class TestInstallation:
    def test_serialization_with_webhook_and_actions(self):
        now = datetime.now(tz=timezone.utc)
        installation = Installation(
            account_id="acc-1",
            workspace_id="ws-1",
            installed_at=now,
            updated_at=now,
            installed_by_user_id="user-1",
            webhook=WebhookRecord(
                webhook_id="wh-1",
                secret="s1",
                events=["file.ready"],
                url="https://myapp.com",
            ),
            actions=[
                ActionRecord(
                    action_id="act-1",
                    secret="s2",
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                    url="https://myapp.com",
                ),
            ],
        )
        data = installation.model_dump(mode="json")
        restored = Installation.model_validate(data)
        assert restored.account_id == "acc-1"
        assert restored.webhook is not None
        assert restored.webhook.webhook_id == "wh-1"
        assert len(restored.actions) == 1
        assert restored.actions[0].name == "Transcribe"

    def test_serialization_without_webhook(self):
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
        data = installation.model_dump(mode="json")
        restored = Installation.model_validate(data)
        assert restored.webhook is None
        assert restored.actions == []


class TestHandlerManifest:
    def test_webhooks_only(self):
        manifest = HandlerManifest(
            webhook_events=["file.ready", "comment.created"],
            actions=[],
        )
        assert manifest.webhook_events == ["file.ready", "comment.created"]
        assert manifest.actions == []

    def test_actions_only(self):
        manifest = HandlerManifest(
            webhook_events=[],
            actions=[
                ActionManifestEntry(
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                ),
            ],
        )
        assert manifest.webhook_events == []
        assert len(manifest.actions) == 1

    def test_both(self):
        manifest = HandlerManifest(
            webhook_events=["file.ready"],
            actions=[
                ActionManifestEntry(
                    event_type="my_app.transcribe",
                    name="Transcribe",
                    description="Transcribe audio",
                ),
            ],
        )
        assert len(manifest.webhook_events) == 1
        assert len(manifest.actions) == 1

    def test_empty(self):
        manifest = HandlerManifest(webhook_events=[], actions=[])
        assert manifest.webhook_events == []
        assert manifest.actions == []


class TestInstallationDiff:
    def test_has_changes_with_additions(self):
        diff = InstallationDiff(
            webhook_events_added=["file.ready"],
            webhook_events_removed=[],
            actions_added=[],
            actions_removed=[],
            actions_modified=[],
        )
        assert diff.has_changes is True

    def test_has_changes_with_removals(self):
        diff = InstallationDiff(
            webhook_events_added=[],
            webhook_events_removed=["comment.created"],
            actions_added=[],
            actions_removed=[],
            actions_modified=[],
        )
        assert diff.has_changes is True

    def test_has_changes_with_action_added(self):
        diff = InstallationDiff(
            webhook_events_added=[],
            webhook_events_removed=[],
            actions_added=[ActionManifestEntry(event_type="test", name="Test", description="desc")],
            actions_removed=[],
            actions_modified=[],
        )
        assert diff.has_changes is True

    def test_no_changes(self):
        diff = InstallationDiff(
            webhook_events_added=[],
            webhook_events_removed=[],
            actions_added=[],
            actions_removed=[],
            actions_modified=[],
        )
        assert diff.has_changes is False
