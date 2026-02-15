"""Tests for install route handlers."""

import pytest
from starlette.testclient import TestClient

from frameio_kit._oauth import OAuthConfig
from frameio_kit import App, InstallField


@pytest.fixture
def oauth_config():
    return OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_url="https://example.com/auth/callback",
    )


@pytest.fixture
def app_with_handlers(oauth_config):
    app = App(
        oauth=oauth_config,
        install=True,
        name="Test App",
        description="A test integration",
        primary_color="#6366f1",
    )

    @app.on_webhook("file.ready")
    async def on_file_ready(event):
        pass

    @app.on_action("my_app.transcribe", name="Transcribe", description="Transcribe audio")
    async def on_transcribe(event):
        pass

    return app


@pytest.fixture
def app_no_handlers(oauth_config):
    return App(
        oauth=oauth_config,
        install=True,
        name="Test App",
        description="A test integration",
    )


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
            App(install=True)

    def test_install_auto_wires_secret_resolver(self, oauth_config):
        app = App(oauth=oauth_config, install=True, name="Test App")
        assert app._secret_resolver is not None
        assert app._install_secret_resolver is not None

    def test_install_routes_mounted(self, oauth_config):
        app = App(oauth=oauth_config, install=True, name="Test App")
        routes = app._asgi_app.routes
        route_paths = [getattr(r, "path", None) for r in routes]
        assert "/install" in route_paths
        assert "/install/login" in route_paths
        assert "/install/callback" in route_paths
        assert "/install/workspaces" in route_paths
        assert "/install/status" in route_paths
        assert "/install/execute" in route_paths
        assert "/install/uninstall" in route_paths

    def test_handlers_registered_without_secret_when_install_configured(self, oauth_config):
        """Handlers should not raise ValueError when install system provides secret resolver."""
        app = App(oauth=oauth_config, install=True, name="Test App")

        @app.on_webhook("file.ready")
        async def on_file_ready(event):
            pass

        @app.on_action("my_app.transcribe", name="Transcribe", description="Transcribe audio")
        async def on_transcribe(event):
            pass

        assert "file.ready" in app._webhook_handlers
        assert "my_app.transcribe" in app._action_handlers


class TestAllowedAccounts:
    def test_allowed_accounts_passed_to_manager(self, oauth_config):
        app = App(
            oauth=oauth_config,
            install=True,
            name="Test App",
            allowed_accounts=["acc-1", "acc-2"],
        )
        assert app._install_manager is not None
        assert app._install_manager._allowed_accounts == {"acc-1", "acc-2"}

    def test_allowed_accounts_default_none(self, oauth_config):
        app = App(
            oauth=oauth_config,
            install=True,
            name="Test App",
        )
        assert app._install_manager is not None
        assert app._install_manager._allowed_accounts is None


class TestFastAPIMount:
    """Test that frameio-kit works when mounted inside a FastAPI app."""

    def test_install_page_accessible_at_root_mount(self, app_with_handlers):
        from fastapi import FastAPI

        fastapi_app = FastAPI()
        fastapi_app.mount("/", app_with_handlers)

        with TestClient(fastapi_app) as c:
            response = c.get("/install")
            assert response.status_code == 200
            assert "Test App" in response.text
            assert "file.ready" in response.text

    def test_install_page_accessible_at_prefix_mount(self, app_with_handlers):
        from fastapi import FastAPI

        fastapi_app = FastAPI()
        fastapi_app.mount("/frameio", app_with_handlers)

        with TestClient(fastapi_app) as c:
            response = c.get("/frameio/install")
            assert response.status_code == 200
            assert "Test App" in response.text

    def test_auth_routes_accessible_when_mounted(self, app_with_handlers):
        from fastapi import FastAPI

        fastapi_app = FastAPI()
        fastapi_app.mount("/", app_with_handlers)

        with TestClient(fastapi_app) as c:
            response = c.get("/auth/login", follow_redirects=False)
            # Route is reachable (not 404); 400 is expected without valid session state
            assert response.status_code != 404

    def test_fastapi_routes_coexist_with_mount(self, app_with_handlers):
        from fastapi import FastAPI

        fastapi_app = FastAPI()

        @fastapi_app.get("/health")
        async def health():
            return {"status": "healthy"}

        fastapi_app.mount("/", app_with_handlers)

        with TestClient(fastapi_app) as c:
            # FastAPI route works
            response = c.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}

            # Mounted frameio-kit route works
            response = c.get("/install")
            assert response.status_code == 200
            assert "Test App" in response.text


class TestInstallFieldsInRoutes:
    @pytest.fixture
    def app_with_fields(self, oauth_config):
        app = App(
            oauth=oauth_config,
            install=True,
            name="Test App",
            install_fields=[
                InstallField(name="api_key", label="API Key", type="password", required=True, description="Your key"),
                InstallField(
                    name="environment",
                    label="Environment",
                    type="select",
                    options=("production", "staging"),
                    default="production",
                ),
            ],
        )

        @app.on_webhook("file.ready")
        async def on_file_ready(event):
            pass

        return app

    @pytest.fixture
    def client_with_fields(self, app_with_fields):
        with TestClient(app_with_fields) as c:
            yield c

    def test_install_fields_on_app_state(self, app_with_fields):
        assert len(app_with_fields._install_fields) == 2
        assert app_with_fields._install_fields[0].name == "api_key"
        assert app_with_fields._install_fields[1].name == "environment"

    @pytest.fixture
    def _session_cookie(self, app_with_fields):
        """Create a valid signed session cookie and store session data."""
        import base64

        manager = app_with_fields._install_manager
        encryption = manager.encryption

        state_serializer = app_with_fields._oauth_manager.state_serializer

        # Encrypt a fake access token and store session data
        encrypted_token = encryption.encrypt(b"fake-access-token")
        session_key = "test-session-key"
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            manager.storage.put(
                f"install_session:{session_key}",
                {"encrypted_access_token": base64.b64encode(encrypted_token).decode("utf-8")},
                ttl=1800,
            )
        )

        # Create signed cookie
        cookie_value = state_serializer.dumps({"session_key": session_key})
        return cookie_value

    def test_required_field_validation_returns_400(self, app_with_fields, _session_cookie):
        """POST /install/execute with missing required field returns 400."""
        with TestClient(app_with_fields) as client:
            response = client.post(
                "/install/execute",
                data={
                    "account_id": "12345678-1234-1234-1234-123456789abc",
                    "workspace_id": "12345678-1234-1234-1234-123456789abc",
                    "config_environment": "production",
                    # config_api_key intentionally missing
                },
                cookies={"install_session": _session_cookie},
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 400
            assert "Missing Required Fields" in response.text
            assert "API Key" in response.text

    def test_required_sensitive_field_allowed_empty_on_update(self, app_with_fields, _session_cookie):
        """Required sensitive fields can be empty on update when they already have stored values."""
        import asyncio

        manager = app_with_fields._install_manager

        # Pre-store an installation with an existing config (simulates a previous install)
        from frameio_kit._install_models import Installation
        from datetime import datetime, timezone

        installation = Installation(
            account_id="12345678-1234-1234-1234-123456789abc",
            workspace_id="12345678-1234-1234-1234-123456789abc",
            installed_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            webhook=None,
            actions=[],
            config={"api_key": "existing-secret", "environment": "production"},
        )
        asyncio.get_event_loop().run_until_complete(manager._store_installation(installation))

        with TestClient(app_with_fields) as client:
            response = client.post(
                "/install/execute",
                data={
                    "account_id": "12345678-1234-1234-1234-123456789abc",
                    "workspace_id": "12345678-1234-1234-1234-123456789abc",
                    "config_environment": "staging",
                    # config_api_key intentionally empty — should be allowed on update
                },
                cookies={"install_session": _session_cookie},
                headers={"HX-Request": "true"},
            )
            # Should NOT get 400 for missing required field
            assert response.status_code != 400
