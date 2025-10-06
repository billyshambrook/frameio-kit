"""Tests for RequireAuth functionality in frameio-kit."""

import json
import time

import httpx
import pytest

from frameio_kit import ActionEvent, App, InMemoryTokenStore, RequireAuth


@pytest.fixture
def sample_secret():
    """A sample secret key for testing."""
    return "my_action_secret"


@pytest.fixture
def action_payload():
    """A sample action payload."""
    return {
        "type": "test.action",
        "account_id": "acc_123",
        "action_id": "act_123",
        "interaction_id": "int_123",
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
        "data": None,
    }


async def test_require_auth_returns_message_with_url(
    action_payload, sample_secret, create_valid_signature
):
    """Test that returning RequireAuth generates a proper authorization message."""
    token_store = InMemoryTokenStore()
    app = App(
        oauth_client_id="test_client_id",
        oauth_client_secret="test_client_secret",
        oauth_redirect_uri="https://test.com/oauth/callback",
        token_store=token_store,
    )

    @app.on_action("test.action", name="Test Action", description="Test", secret=sample_secret)
    async def test_action(event: ActionEvent):
        return RequireAuth()

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

        assert response.status_code == 200
        data = response.json()

        # Should return a Message
        assert "title" in data
        assert "description" in data

        # Default title
        assert data["title"] == "Authorization Required"

        # Description should contain the auth URL
        assert "https://applications.frame.io/oauth2/auth" in data["description"]
        assert "client_id=test_client_id" in data["description"]
        assert "state=user_123%3Aint_123" in data["description"]
        assert "After authorizing, trigger this action again" in data["description"]


async def test_require_auth_with_custom_title(
    action_payload, sample_secret, create_valid_signature
):
    """Test RequireAuth with custom title."""
    token_store = InMemoryTokenStore()
    app = App(
        oauth_client_id="test_client_id",
        oauth_client_secret="test_client_secret",
        oauth_redirect_uri="https://test.com/oauth/callback",
        token_store=token_store,
    )

    @app.on_action("test.action", name="Test Action", description="Test", secret=sample_secret)
    async def test_action(event: ActionEvent):
        return RequireAuth(title="Connect Your Account")

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

        assert response.status_code == 200
        data = response.json()

        assert data["title"] == "Connect Your Account"


async def test_require_auth_with_custom_description(
    action_payload, sample_secret, create_valid_signature
):
    """Test RequireAuth with custom description."""
    token_store = InMemoryTokenStore()
    app = App(
        oauth_client_id="test_client_id",
        oauth_client_secret="test_client_secret",
        oauth_redirect_uri="https://test.com/oauth/callback",
        token_store=token_store,
    )

    @app.on_action("test.action", name="Test Action", description="Test", secret=sample_secret)
    async def test_action(event: ActionEvent):
        return RequireAuth(
            description="To export files, we need access to your Frame.io account."
        )

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

        assert response.status_code == 200
        data = response.json()

        # Should include custom description
        assert "To export files, we need access to your Frame.io account." in data["description"]
        # And still include the auth URL
        assert "https://applications.frame.io/oauth2/auth" in data["description"]


async def test_require_auth_without_oauth_configured(
    action_payload, sample_secret, create_valid_signature
):
    """Test that RequireAuth fails gracefully when OAuth is not configured."""
    app = App()  # No OAuth credentials

    @app.on_action("test.action", name="Test Action", description="Test", secret=sample_secret)
    async def test_action(event: ActionEvent):
        return RequireAuth()

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

        assert response.status_code == 500
        assert "OAuth not configured" in response.text


async def test_require_auth_complete_flow(
    action_payload, sample_secret, create_valid_signature
):
    """Test complete flow: RequireAuth → authorize → action succeeds."""
    token_store = InMemoryTokenStore()
    app = App(
        token="app_token",
        oauth_client_id="test_client_id",
        oauth_client_secret="test_client_secret",
        oauth_redirect_uri="https://test.com/oauth/callback",
        token_store=token_store,
    )

    call_log = []

    @app.on_action("test.action", name="Test Action", description="Test", secret=sample_secret)
    async def test_action(event: ActionEvent):
        user_token = await app.oauth.get_user_token(event.user.id)

        if not user_token:
            return RequireAuth()

        call_log.append("authorized")
        return None

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        # First call - no token, should get RequireAuth message
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Authorization Required"

        # Manually store a token (simulating OAuth callback)
        await token_store.save_token(
            "user_123",
            {
                "access_token": "test_token",
                "refresh_token": "test_refresh",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

        # Second call - with token, should succeed
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200
        assert len(call_log) == 1
        assert call_log[0] == "authorized"
