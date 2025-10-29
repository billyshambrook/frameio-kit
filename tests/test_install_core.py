"""Tests for installation system core infrastructure (models, manifest, manager)."""

import pytest
from key_value.aio.stores.memory import MemoryStore

from frameio_kit._encryption import TokenEncryption
from frameio_kit._install_manager import InstallationManager
from frameio_kit._install_models import (
    InstallationConfig,
    InstallationRecord,
    InstallationResult,
    InstalledAction,
    InstalledWebhook,
)
from frameio_kit._manifest import ActionManifestItem, AppManifest, WebhookManifestItem


class TestInstallationModels:
    """Test installation data models."""

    def test_installation_config_creation(self):
        """Test creating an InstallationConfig."""
        config = InstallationConfig(
            enabled=True,
            app_name="Test App",
            app_description="Test Description",
            app_icon_url="https://example.com/icon.png",
        )

        assert config.enabled is True
        assert config.app_name == "Test App"
        assert config.app_description == "Test Description"
        assert config.app_icon_url == "https://example.com/icon.png"
        assert config.include_actions is None
        assert config.include_webhooks is None

    def test_installation_config_with_filters(self):
        """Test InstallationConfig with filters."""
        config = InstallationConfig(
            enabled=True,
            app_name="Test App",
            app_description="Test Description",
            include_actions=["action1", "action2"],
            include_webhooks=["webhook1"],
        )

        assert config.include_actions == ["action1", "action2"]
        assert config.include_webhooks == ["webhook1"]

    def test_installation_record_creation(self):
        """Test creating an InstallationRecord."""
        record = InstallationRecord(
            workspace_id="ws_123",
            account_id="acc_456",
            user_id="user_789",
            status="active",
        )

        assert record.workspace_id == "ws_123"
        assert record.account_id == "acc_456"
        assert record.user_id == "user_789"
        assert record.status == "active"
        assert record.actions == []
        assert record.webhooks == []

    def test_installed_action_creation(self):
        """Test creating an InstalledAction."""
        action = InstalledAction(
            action_id="action_123",
            event_type="my_app.test",
            name="Test Action",
            description="Test Description",
            secret="secret_abc",
        )

        assert action.action_id == "action_123"
        assert action.event_type == "my_app.test"
        assert action.name == "Test Action"
        assert action.secret == "secret_abc"

    def test_installed_webhook_creation(self):
        """Test creating an InstalledWebhook."""
        webhook = InstalledWebhook(
            webhook_id="webhook_123",
            event_types=["file.ready", "file.deleted"],
            name="Test Webhook",
            secret="secret_xyz",
        )

        assert webhook.webhook_id == "webhook_123"
        assert webhook.event_types == ["file.ready", "file.deleted"]
        assert webhook.name == "Test Webhook"
        assert webhook.secret == "secret_xyz"

    def test_installation_result_creation(self):
        """Test creating an InstallationResult."""
        result = InstallationResult(
            success=True,
            workspace_results={"ws_1": True, "ws_2": False},
            errors={"ws_2": "Some error"},
        )

        assert result.success is True
        assert result.workspace_results == {"ws_1": True, "ws_2": False}
        assert result.errors == {"ws_2": "Some error"}


class TestManifest:
    """Test app manifest generation."""

    def test_action_manifest_item_creation(self):
        """Test creating an ActionManifestItem."""
        action = ActionManifestItem(
            event_type="my_app.test",
            name="Test Action",
            description="Test Description",
            require_user_auth=True,
        )

        assert action.event_type == "my_app.test"
        assert action.name == "Test Action"
        assert action.description == "Test Description"
        assert action.require_user_auth is True

    def test_webhook_manifest_item_creation(self):
        """Test creating a WebhookManifestItem."""
        webhook = WebhookManifestItem(
            event_types=["file.ready", "file.deleted"],
            description="Test Webhook",
        )

        assert webhook.event_types == ["file.ready", "file.deleted"]
        assert webhook.description == "Test Webhook"

    def test_app_manifest_creation(self):
        """Test creating an AppManifest."""
        manifest = AppManifest(
            name="Test App",
            description="Test Description",
            base_url="https://example.com",
            actions=[
                ActionManifestItem(
                    event_type="my_app.test",
                    name="Test Action",
                    description="Test Description",
                )
            ],
            webhooks=[
                WebhookManifestItem(
                    event_types=["file.ready"],
                    description="Test Webhook",
                )
            ],
        )

        assert manifest.name == "Test App"
        assert manifest.description == "Test Description"
        assert manifest.base_url == "https://example.com"
        assert len(manifest.actions) == 1
        assert len(manifest.webhooks) == 1

    def test_manifest_hash_consistency(self):
        """Test that manifest hash is consistent."""
        manifest1 = AppManifest(
            name="Test App",
            description="Test Description",
            base_url="https://example.com",
            actions=[],
            webhooks=[],
        )

        manifest2 = AppManifest(
            name="Test App",
            description="Test Description",
            base_url="https://example.com",
            actions=[],
            webhooks=[],
        )

        # Same manifest should have same hash
        assert manifest1.compute_hash() == manifest2.compute_hash()

    def test_manifest_hash_difference(self):
        """Test that different manifests have different hashes."""
        manifest1 = AppManifest(
            name="Test App 1",
            description="Test Description",
            base_url="https://example.com",
            actions=[],
            webhooks=[],
        )

        manifest2 = AppManifest(
            name="Test App 2",
            description="Test Description",
            base_url="https://example.com",
            actions=[],
            webhooks=[],
        )

        # Different manifests should have different hashes
        assert manifest1.compute_hash() != manifest2.compute_hash()


class TestInstallationManager:
    """Test installation manager."""

    @pytest.fixture
    def manager(self):
        """Create a test installation manager."""
        from frameio_kit import App

        # Create a minimal app for testing
        app = App(token="test_token")

        # Create minimal manifest
        manifest = AppManifest(
            name="Test App",
            description="Test Description",
            base_url="https://example.com",
            actions=[],
            webhooks=[],
        )

        # Create encryption
        encryption = TokenEncryption()

        # Create manager
        return InstallationManager(
            app=app,
            storage=MemoryStore(),
            encryption=encryption,
            manifest=manifest,
        )

    def test_manager_initialization(self, manager):
        """Test that manager initializes correctly."""
        assert manager is not None
        assert manager.manifest is not None
        assert manager.storage is not None
        assert manager.encryption is not None

    def test_make_installation_key(self, manager):
        """Test installation key generation."""
        key = manager._make_installation_key("workspace_123")
        assert key == "install:workspace_123"

    def test_make_index_key(self, manager):
        """Test index key generation."""
        key = manager._make_index_key("user_123")
        assert key == "install:index:user_123"

    async def test_get_nonexistent_installation(self, manager):
        """Test getting a non-existent installation."""
        installation = await manager.get_installation("workspace_123")
        assert installation is None

    async def test_store_and_retrieve_installation(self, manager):
        """Test storing and retrieving an installation."""
        # Create a test installation record
        record = InstallationRecord(
            workspace_id="ws_123",
            account_id="acc_456",
            user_id="user_789",
            status="active",
        )

        # Store it
        await manager._store_installation(record)

        # Retrieve it
        retrieved = await manager.get_installation("ws_123")

        assert retrieved is not None
        assert retrieved.workspace_id == "ws_123"
        assert retrieved.account_id == "acc_456"
        assert retrieved.user_id == "user_789"
        assert retrieved.status == "active"
