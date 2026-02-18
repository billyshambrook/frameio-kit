"""Tests for InstallField model, validation, context, and form extraction."""

import pytest

from frameio_kit import App, InstallField, get_install_config
from frameio_kit._context import _install_config_context
from frameio_kit._exceptions import ConfigurationError
from frameio_kit._install_models import Installation
from frameio_kit._oauth import OAuthConfig


class TestInstallFieldDefaults:
    def test_default_type_is_text(self):
        field = InstallField(name="foo", label="Foo")
        assert field.type == "text"

    def test_default_required_is_false(self):
        field = InstallField(name="foo", label="Foo")
        assert field.required is False

    def test_default_sensitive_none(self):
        field = InstallField(name="foo", label="Foo")
        assert field.sensitive is None

    def test_is_sensitive_auto_true_for_password(self):
        field = InstallField(name="api_key", label="API Key", type="password")
        assert field.is_sensitive is True

    def test_is_sensitive_auto_false_for_text(self):
        field = InstallField(name="url", label="URL", type="text")
        assert field.is_sensitive is False

    def test_is_sensitive_explicit_override(self):
        field = InstallField(name="token", label="Token", type="text", sensitive=True)
        assert field.is_sensitive is True

    def test_is_sensitive_explicit_false_for_password(self):
        field = InstallField(name="pass", label="Pass", type="password", sensitive=False)
        assert field.is_sensitive is False

    def test_frozen(self):
        field = InstallField(name="foo", label="Foo")
        with pytest.raises(AttributeError):
            field.name = "bar"  # type: ignore[misc]

    def test_options_tuple(self):
        field = InstallField(name="env", label="Env", type="select", options=("prod", "staging"))
        assert field.options == ("prod", "staging")

    def test_default_value(self):
        field = InstallField(name="env", label="Env", default="prod")
        assert field.default == "prod"


class TestInstallationWithConfig:
    def test_installation_config_default_none(self):
        from datetime import datetime, timezone

        inst = Installation(
            account_id="a",
            workspace_id="w",
            installed_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        assert inst.config is None

    def test_installation_with_config(self):
        from datetime import datetime, timezone

        inst = Installation(
            account_id="a",
            workspace_id="w",
            installed_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            config={"api_key": "secret123", "env": "prod"},
        )
        assert inst.config == {"api_key": "secret123", "env": "prod"}

    def test_installation_config_round_trip_serialization(self):
        from datetime import datetime, timezone

        config = {"api_key": "secret123", "env": "prod"}
        inst = Installation(
            account_id="a",
            workspace_id="w",
            installed_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            config=config,
        )
        data = inst.model_dump(mode="json")
        restored = Installation.model_validate(data)
        assert restored.config == config


class TestGetInstallConfig:
    def test_raises_outside_context(self):
        with pytest.raises(RuntimeError, match="requires install_fields.*stored install config"):
            get_install_config()

    def test_returns_value_when_set(self):
        token = _install_config_context.set({"api_key": "test123"})
        try:
            config = get_install_config()
            assert config == {"api_key": "test123"}
        finally:
            _install_config_context.reset(token)


class TestAppInstallFieldsValidation:
    @pytest.fixture
    def oauth_config(self):
        return OAuthConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_url="https://example.com/auth/callback",
        )

    def test_install_fields_requires_install(self, oauth_config):
        """install_fields without install=True should result in empty tuple (no validation error)."""
        app = App(oauth=oauth_config, install_fields=[InstallField(name="foo", label="Foo")])
        assert app._install_fields == ()

    def test_valid_install_fields(self, oauth_config):
        fields = [
            InstallField(name="api_key", label="API Key", type="password", required=True),
            InstallField(name="env", label="Environment", type="select", options=("prod", "staging")),
        ]
        app = App(oauth=oauth_config, install=True, install_fields=fields)
        assert len(app._install_fields) == 2

    def test_duplicate_names_raises(self, oauth_config):
        fields = [
            InstallField(name="foo", label="Foo"),
            InstallField(name="foo", label="Foo 2"),
        ]
        with pytest.raises(ConfigurationError, match="Duplicate install field name"):
            App(oauth=oauth_config, install=True, install_fields=fields)

    def test_reserved_name_account_id(self, oauth_config):
        fields = [InstallField(name="account_id", label="Account")]
        with pytest.raises(ConfigurationError, match="Reserved install field name"):
            App(oauth=oauth_config, install=True, install_fields=fields)

    def test_reserved_name_workspace_id(self, oauth_config):
        fields = [InstallField(name="workspace_id", label="Workspace")]
        with pytest.raises(ConfigurationError, match="Reserved install field name"):
            App(oauth=oauth_config, install=True, install_fields=fields)

    def test_invalid_type_raises(self, oauth_config):
        fields = [InstallField(name="foo", label="Foo", type="checkbox")]
        with pytest.raises(ConfigurationError, match="Invalid install field type"):
            App(oauth=oauth_config, install=True, install_fields=fields)

    def test_select_without_options_raises(self, oauth_config):
        fields = [InstallField(name="env", label="Env", type="select")]
        with pytest.raises(ConfigurationError, match="must have options"):
            App(oauth=oauth_config, install=True, install_fields=fields)

    def test_select_invalid_default_raises(self, oauth_config):
        fields = [InstallField(name="env", label="Env", type="select", options=("prod", "staging"), default="dev")]
        with pytest.raises(ConfigurationError, match="Invalid default 'dev'.*Must be one of: prod, staging"):
            App(oauth=oauth_config, install=True, install_fields=fields)

    def test_install_fields_stored_as_tuple(self, oauth_config):
        fields = [InstallField(name="foo", label="Foo")]
        app = App(oauth=oauth_config, install=True, install_fields=fields)
        assert isinstance(app._install_fields, tuple)

    def test_install_fields_on_app_state(self, oauth_config):
        fields = [InstallField(name="foo", label="Foo")]
        app = App(oauth=oauth_config, install=True, install_fields=fields)
        assert app._install_fields == (InstallField(name="foo", label="Foo"),)

    def test_install_fields_passed_to_manager(self, oauth_config):
        fields = [
            InstallField(name="api_key", label="API Key", type="password"),
        ]
        app = App(oauth=oauth_config, install=True, install_fields=fields)
        assert app._install_manager is not None
        assert len(app._install_manager._install_fields) == 1
        assert app._install_manager._sensitive_field_names == frozenset({"api_key"})
