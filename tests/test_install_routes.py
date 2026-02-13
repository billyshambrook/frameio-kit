"""Tests for install route handlers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from frameio_kit._encryption import TokenEncryption
from frameio_kit._install_config import InstallConfig
from frameio_kit._install_models import ActionManifestEntry, ActionRecord, HandlerManifest, Installation, WebhookRecord
from frameio_kit._oauth import OAuthConfig
from frameio_kit import App

TEST_KEY = TokenEncryption.generate_key()


@pytest.fixture
def install_config():
    return InstallConfig(
        app_name="Test App",
        app_description="A test integration",
        primary_color="#6366f1",
    )


@pytest.fixture
def oauth_config():
    return OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_url="https://example.com/auth/callback",
        encryption_key=TEST_KEY,
    )


@pytest.fixture
def app_with_handlers(oauth_config, install_config):
    app = App(
        oauth=oauth_config,
        install=install_config,
    )

    @app.on_webhook("file.ready")
    async def on_file_ready(event):
        pass

    @app.on_action("my_app.transcribe", name="Transcribe", description="Transcribe audio")
    async def on_transcribe(event):
        pass

    return app


@pytest.fixture
def app_no_handlers(oauth_config, install_config):
    return App(oauth=oauth_config, install=install_config)


@pytest.fixture
def client_with_handlers(app_with_handlers):
    with TestClient(app_with_handlers) as c:
        yield c


@pytest.fixture
def client_no_handlers(app_no_handlers):
    with TestClient(app_no_handlers) as c:
        yield c


class TestInstallLandingPage:
    def test_unauthenticated_shows_landing_page(self, client_with_handlers):
        response = client_with_handlers.get("/install")
        assert response.status_code == 200
        assert "Test App" in response.text
        assert "A test integration" in response.text
        assert "Login with Adobe" in response.text

    def test_unauthenticated_shows_handler_manifest(self, client_with_handlers):
        response = client_with_handlers.get("/install")
        assert response.status_code == 200
        assert "file.ready" in response.text
        assert "Transcribe" in response.text
        assert "Transcribe audio" in response.text

    def test_branding_colors_applied(self, client_with_handlers):
        response = client_with_handlers.get("/install")
        assert response.status_code == 200
        assert "#6366f1" in response.text

    def test_powered_by_shown(self, client_with_handlers):
        response = client_with_handlers.get("/install")
        assert "Powered by" in response.text
        assert "frameio-kit" in response.text


class TestInstallLogin:
    def test_redirects_to_adobe(self, client_no_handlers):
        response = client_no_handlers.get("/install/login", follow_redirects=False)
        assert response.status_code == 307
        assert "location" in response.headers
        location = response.headers["location"]
        assert "ims-na1.adobelogin.com" in location
        assert "client_id=test_client_id" in location


class TestInstallCallback:
    def test_callback_with_error(self, client_no_handlers):
        response = client_no_handlers.get("/install/callback", params={"error": "access_denied"})
        assert response.status_code == 400
        assert "Authentication Failed" in response.text

    def test_callback_missing_code(self, client_no_handlers):
        response = client_no_handlers.get("/install/callback", params={"state": "test"})
        assert response.status_code == 400
        assert "Missing code or state" in response.text

    def test_callback_missing_state(self, client_no_handlers):
        response = client_no_handlers.get("/install/callback", params={"code": "test"})
        assert response.status_code == 400
        assert "Missing code or state" in response.text

    def test_callback_invalid_state(self, client_no_handlers):
        response = client_no_handlers.get("/install/callback", params={"code": "test_code", "state": "invalid"})
        assert response.status_code == 400
        assert "Invalid" in response.text


class TestInstallWorkspaces:
    def test_requires_session(self, client_no_handlers):
        response = client_no_handlers.get(
            "/install/workspaces",
            params={"account_id": "12345678-1234-1234-1234-123456789abc"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers

    def test_empty_account_id_redirects_without_session(self, client_no_handlers):
        response = client_no_handlers.get("/install/workspaces", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/install"

    def test_invalid_uuid_redirects_without_session(self, client_no_handlers):
        response = client_no_handlers.get(
            "/install/workspaces", params={"account_id": "not-a-uuid"}, follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == "/install"


class TestInstallStatus:
    def test_requires_session(self, client_no_handlers):
        response = client_no_handlers.get(
            "/install/status",
            params={
                "account_id": "12345678-1234-1234-1234-123456789abc",
                "workspace_id": "12345678-1234-1234-1234-123456789abc",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers

    def test_empty_params_redirects_without_session(self, client_no_handlers):
        response = client_no_handlers.get("/install/status", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/install"


class TestInstallExecute:
    def test_requires_session(self, client_no_handlers):
        response = client_no_handlers.post(
            "/install/execute",
            data={
                "account_id": "12345678-1234-1234-1234-123456789abc",
                "workspace_id": "12345678-1234-1234-1234-123456789abc",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers


class TestInstallUninstall:
    def test_requires_session(self, client_no_handlers):
        response = client_no_handlers.post(
            "/install/uninstall",
            data={
                "account_id": "12345678-1234-1234-1234-123456789abc",
                "workspace_id": "12345678-1234-1234-1234-123456789abc",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers


class TestAppInstallConfiguration:
    def test_install_requires_oauth(self):
        with pytest.raises(Exception, match="OAuth"):
            App(install=InstallConfig(app_name="Test"))

    def test_install_auto_wires_secret_resolver(self, oauth_config, install_config):
        app = App(oauth=oauth_config, install=install_config)
        assert app._secret_resolver is not None
        assert app._install_secret_resolver is not None

    def test_install_preserves_explicit_resolver(self, oauth_config, install_config):
        class CustomResolver:
            async def get_webhook_secret(self, event):
                return "custom"

            async def get_action_secret(self, event):
                return "custom"

        custom = CustomResolver()
        app = App(oauth=oauth_config, install=install_config, secret_resolver=custom)
        assert app._secret_resolver is custom
        assert app._install_secret_resolver is None

    def test_install_routes_mounted(self, oauth_config, install_config):
        app = App(oauth=oauth_config, install=install_config)
        routes = app._asgi_app.routes
        route_paths = [getattr(r, "path", None) for r in routes]
        assert "/install" in route_paths
        assert "/install/login" in route_paths
        assert "/install/callback" in route_paths
        assert "/install/workspaces" in route_paths
        assert "/install/status" in route_paths
        assert "/install/execute" in route_paths
        assert "/install/uninstall" in route_paths

    def test_handlers_registered_without_secret_when_install_configured(self, oauth_config, install_config):
        """Handlers should not raise ValueError when install system provides secret resolver."""
        app = App(oauth=oauth_config, install=install_config)

        @app.on_webhook("file.ready")
        async def on_file_ready(event):
            pass

        @app.on_action("my_app.transcribe", name="Transcribe", description="Transcribe audio")
        async def on_transcribe(event):
            pass

        assert "file.ready" in app._webhook_handlers
        assert "my_app.transcribe" in app._action_handlers
