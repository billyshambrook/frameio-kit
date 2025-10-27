"""Tests for the app installation system."""

import pytest
from cryptography.fernet import Fernet
from key_value.aio.stores.memory import MemoryStore

from frameio_kit import App, InstallationConfig, OAuthConfig
from frameio_kit._manifest import AppManifest


@pytest.fixture
def oauth_config():
    """OAuth configuration for testing."""
    # Generate a valid Fernet key for testing
    test_key = Fernet.generate_key().decode()
    return OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        base_url="https://example.com",
        storage=MemoryStore(),
        encryption_key=test_key,
    )


@pytest.fixture
def installation_config():
    """Installation configuration for testing."""
    return InstallationConfig(
        enabled=True,
        app_name="Test App",
        app_description="A test application",
        app_icon_url="https://example.com/icon.png",
    )


def test_app_without_installation(oauth_config):
    """Test that app works without installation config."""
    app = App(
        token="test_token",
        oauth=oauth_config,
    )

    assert app._installation_manager is None


def test_app_with_installation(oauth_config, installation_config):
    """Test that app initializes installation manager when configured."""
    app = App(
        token="test_token",
        oauth=oauth_config,
        installation=installation_config,
    )

    # Should have installation manager
    assert app._installation_manager is not None
    assert app.installation_manager is not None


def test_app_installation_without_oauth(installation_config):
    """Test that installation requires OAuth."""
    with pytest.raises(RuntimeError, match="Installation requires OAuth configuration"):
        App(
            token="test_token",
            installation=installation_config,
        )


def test_manifest_auto_discovery(oauth_config, installation_config):
    """Test that manifest auto-discovers registered handlers."""
    app = App(
        token="test_token",
        oauth=oauth_config,
        installation=installation_config,
    )

    # Register some handlers
    @app.on_action(
        event_type="test.action1",
        name="Test Action 1",
        description="First test action",
        secret="secret1",
    )
    async def action1(event):
        pass

    @app.on_action(
        event_type="test.action2",
        name="Test Action 2",
        description="Second test action",
        secret="secret2",
    )
    async def action2(event):
        pass

    @app.on_webhook(
        event_type="file.ready",
        secret="webhook_secret",
    )
    async def webhook1(event):
        pass

    # Generate manifest
    manifest = AppManifest.from_app(
        app=app,
        app_name="Test App",
        app_description="Test Description",
        base_url="https://example.com",
    )

    # Verify actions discovered
    assert len(manifest.actions) == 2
    action_types = {a.event_type for a in manifest.actions}
    assert "test.action1" in action_types
    assert "test.action2" in action_types

    # Verify webhooks discovered
    assert len(manifest.webhooks) == 1
    assert "file.ready" in manifest.webhooks[0].event_types


def test_manifest_filtering(oauth_config, installation_config):
    """Test that manifest respects include filters."""
    app = App(
        token="test_token",
        oauth=oauth_config,
        installation=installation_config,
    )

    # Register handlers
    @app.on_action(
        event_type="test.action1",
        name="Test Action 1",
        description="First test action",
        secret="secret1",
    )
    async def action1(event):
        pass

    @app.on_action(
        event_type="test.action2",
        name="Test Action 2",
        description="Second test action",
        secret="secret2",
    )
    async def action2(event):
        pass

    # Generate manifest with filter
    manifest = AppManifest.from_app(
        app=app,
        app_name="Test App",
        app_description="Test Description",
        base_url="https://example.com",
        include_actions=["test.action1"],  # Only include action1
    )

    # Verify only action1 included
    assert len(manifest.actions) == 1
    assert manifest.actions[0].event_type == "test.action1"


def test_manifest_hash():
    """Test that manifest hash is computed correctly."""
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

    # Different manifest should have different hash
    manifest3 = AppManifest(
        name="Different App",
        description="Test Description",
        base_url="https://example.com",
        actions=[],
        webhooks=[],
    )

    assert manifest1.compute_hash() != manifest3.compute_hash()


def test_installation_routes_added(oauth_config, installation_config):
    """Test that installation routes are added to the app."""
    app = App(
        token="test_token",
        oauth=oauth_config,
        installation=installation_config,
    )

    # Check that installation routes exist
    routes = [route.path for route in app._asgi_app.routes]

    assert "/install" in routes
    assert "/install/oauth/login" in routes
    assert "/install/oauth/callback" in routes
    assert "/install/workspaces" in routes
    assert "/install/process" in routes
    assert "/install/manage" in routes
    assert "/install/uninstall" in routes
