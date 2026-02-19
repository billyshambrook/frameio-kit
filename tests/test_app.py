import json
import time

import httpx
import pytest

from frameio_kit import ActionEvent, AnyEvent, AnyResponse, App, Message, Middleware, NextFunc, WebhookEvent

# --- Middleware Test Classes ---


class CallMiddleware(Middleware):
    def __init__(self, call_log: list):
        self.call_log = call_log

    async def __call__(self, event: AnyEvent, next: NextFunc) -> AnyResponse:
        self.call_log.append(f"call_before_{event.type}")
        response = await next(event)
        self.call_log.append(f"call_after_{event.type}")
        return response


class WebhookMiddleware(Middleware):
    def __init__(self, call_log: list):
        self.call_log = call_log

    async def on_webhook(self, event: WebhookEvent, next: NextFunc) -> AnyResponse:
        self.call_log.append(f"webhook_before_{event.type}")
        response = await next(event)
        self.call_log.append(f"webhook_after_{event.type}")
        return response


class ActionMiddleware(Middleware):
    def __init__(self, call_log: list):
        self.call_log = call_log

    async def on_action(self, event: ActionEvent, next: NextFunc) -> AnyResponse:
        self.call_log.append(f"action_before_{event.type}")
        response = await next(event)
        self.call_log.append(f"action_after_{event.type}")
        return response


@pytest.fixture
def sample_secret():
    """A sample secret key for testing."""
    return "my_app_secret"


@pytest.fixture
def webhook_payload():
    """A sample webhook payload dictionary."""
    return {
        "type": "file.ready",
        "account": {"id": "acc_123"},
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
    }


@pytest.fixture
def action_payload(webhook_payload) -> dict:
    """A sample action payload with form data."""
    payload = webhook_payload.copy()
    del payload["account"]  # Custom actions have a flat account_id
    resource = payload.pop("resource")
    payload["account_id"] = "acc_123"
    payload["action_id"] = "act_123"
    payload["interaction_id"] = "int_123"
    payload["type"] = "transcribe.file"
    payload["resources"] = [resource]
    payload["data"] = {"language": "en-US"}
    return payload


async def test_app_responds_404_for_invalid_path():
    """Tests that the app returns 404 for requests to undefined paths."""
    app = App()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/invalid-path")
        assert response.status_code == 404


async def test_app_responds_405_for_get_request():
    """Tests that the app returns 405 for methods other than POST."""
    app = App()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 405


async def test_handle_request_returns_400_for_invalid_json():
    """Tests that a 400 is returned for a malformed JSON body."""
    app = App()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content="not valid json")
        assert response.status_code == 400
        assert "Invalid JSON" in response.text


async def test_handle_request_returns_400_for_missing_type_field():
    """Tests that a 400 is returned if the 'type' field is missing from the payload."""
    app = App()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", json={"data": "some_data"})
        assert response.status_code == 400
        assert "Payload missing 'type' field" in response.text


async def test_handle_request_returns_404_for_unregistered_event(
    webhook_payload, sample_secret, create_valid_signature
):
    """Tests that a 404 is returned when no handler is registered for an event."""
    app = App()  # No handlers registered
    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 404
        assert "No handler registered" in response.text


async def test_handle_request_returns_401_for_invalid_signature(webhook_payload, sample_secret):
    """Tests that a 401 is returned for an invalid signature."""
    app = App()

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        pass

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": "v0=invalid_signature_string",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 401
        assert "Invalid signature" in response.text


async def test_handle_request_executes_handler_for_valid_request(
    webhook_payload, sample_secret, create_valid_signature
):
    """Tests the full happy path: a valid request correctly calls the registered handler."""

    # Use a mutable list to track if the handler was called and with what event
    call_log = []

    app = App()

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handle_file_ready(event: WebhookEvent):
        call_log.append(event)
        return None

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200
        assert response.text == "OK"

    # Assert that the handler was called exactly once
    assert len(call_log) == 1
    # Assert that the payload was correctly parsed into a Pydantic model
    event_arg = call_log[0]
    assert isinstance(event_arg, WebhookEvent)
    assert event_arg.resource.id == "file_123"
    assert event_arg.type == "file.ready"
    # Assert that the timestamp was correctly extracted from headers
    assert event_arg.timestamp == ts


async def test_handle_request_serializes_ui_response(action_payload, sample_secret, create_valid_signature):
    """Tests that a Message or Form returned by a handler is correctly serialized to JSON."""
    app = App()

    @app.on_action("transcribe.file", name="Transcribe", description="...", secret=sample_secret)
    async def handler(event: ActionEvent):
        return Message(title="Success", description=f"File {event.resource_ids[0]} sent.")

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"title": "Success", "description": "File file_123 sent."}


async def test_handle_request_returns_500_on_handler_exception(webhook_payload, sample_secret, create_valid_signature):
    """Tests that the app catches exceptions in handlers and returns a 500 status."""
    app = App()

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        raise ValueError("Something went wrong inside the handler!")

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 500
        assert "Internal Server Error" in response.text


async def test_call_middleware_triggers_on_all_events(
    webhook_payload, action_payload, sample_secret, create_valid_signature
):
    call_log = []
    app = App(middleware=[CallMiddleware(call_log)])

    @app.on_webhook("file.ready", secret=sample_secret)
    async def webhook_handler(event: WebhookEvent):
        call_log.append("webhook_handler")

    @app.on_action("transcribe.file", name="...", description="...", secret=sample_secret)
    async def action_handler(event: ActionEvent):
        call_log.append("action_handler")

    # Test webhook
    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        await client.post("/", content=body, headers=headers)

    assert call_log == ["call_before_file.ready", "webhook_handler", "call_after_file.ready"]

    # Test action
    call_log.clear()
    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        await client.post("/", content=body, headers=headers)

    assert call_log == ["call_before_transcribe.file", "action_handler", "call_after_transcribe.file"]


async def test_specific_middleware_triggers_on_correct_events(
    webhook_payload, action_payload, sample_secret, create_valid_signature
):
    call_log = []
    app = App(middleware=[WebhookMiddleware(call_log), ActionMiddleware(call_log)])

    @app.on_webhook("file.ready", secret=sample_secret)
    async def webhook_handler(event: WebhookEvent):
        call_log.append("webhook_handler")

    @app.on_action("transcribe.file", name="...", description="...", secret=sample_secret)
    async def action_handler(event: ActionEvent):
        call_log.append("action_handler")

    # Test webhook
    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        await client.post("/", content=body, headers=headers)

    # ActionMiddleware should not be called
    assert call_log == ["webhook_before_file.ready", "webhook_handler", "webhook_after_file.ready"]

    # Test action
    call_log.clear()
    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        await client.post("/", content=body, headers=headers)

    # WebhookMiddleware should not be called
    assert call_log == ["action_before_transcribe.file", "action_handler", "action_after_transcribe.file"]


async def test_timestamp_exposed_on_webhook_event(webhook_payload, sample_secret, create_valid_signature):
    """Tests that the timestamp is correctly extracted from headers and exposed on WebhookEvent."""
    call_log = []
    app = App()

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1
    event = call_log[0]
    assert event.timestamp == ts


async def test_timestamp_exposed_on_action_event(action_payload, sample_secret, create_valid_signature):
    """Tests that the timestamp is correctly extracted from headers and exposed on ActionEvent."""
    call_log = []
    app = App()

    @app.on_action("transcribe.file", name="Transcribe", description="...", secret=sample_secret)
    async def handler(event: ActionEvent):
        call_log.append(event)

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1
    event = call_log[0]
    assert event.timestamp == ts


async def test_missing_timestamp_header_returns_400(webhook_payload, sample_secret):
    """Tests that a 400 is returned when the X-Frameio-Request-Timestamp header is missing."""
    app = App()

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        pass

    body = json.dumps(webhook_payload).encode()
    # No timestamp header provided - will fail when trying to parse event
    headers = {
        "X-Frameio-Signature": "v0=dummy_signature",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        # Now returns 400 because timestamp header is required for event parsing
        assert response.status_code == 400
        assert "Missing X-Frameio-Request-Timestamp header" in response.text


# --- Secret Defaulting Tests ---


async def test_webhook_uses_env_var_when_no_explicit_secret(
    webhook_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that on_webhook uses WEBHOOK_SECRET env var when secret parameter is not provided."""
    # Set the environment variable
    monkeypatch.setenv("WEBHOOK_SECRET", sample_secret)

    call_log = []
    app = App()

    # No explicit secret provided - should use env var
    @app.on_webhook("file.ready")
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1


async def test_webhook_explicit_secret_takes_precedence_over_env_var(
    webhook_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that explicit secret parameter takes precedence over WEBHOOK_SECRET env var."""
    # Set a different secret in env var
    monkeypatch.setenv("WEBHOOK_SECRET", "env_var_secret")

    call_log = []
    app = App()

    # Explicit secret should be used, not env var
    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        # Use the explicit secret for signature, not env var
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1


def test_webhook_raises_error_when_no_secret_provided(monkeypatch):
    """Tests that ValueError is raised when neither secret parameter nor env var is provided."""
    # Ensure env var is not set
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

    app = App()

    # Should raise ValueError at decorator time
    with pytest.raises(
        ValueError,
        match="Webhook secret must be provided either via 'secret' parameter, app-level secret_resolver, or WEBHOOK_SECRET environment variable",
    ):

        @app.on_webhook("file.ready")
        async def handler(event: WebhookEvent):
            pass


async def test_action_uses_env_var_when_no_explicit_secret(
    action_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that on_action uses CUSTOM_ACTION_SECRET env var when secret parameter is not provided."""
    # Set the environment variable
    monkeypatch.setenv("CUSTOM_ACTION_SECRET", sample_secret)

    call_log = []
    app = App()

    # No explicit secret provided - should use env var
    @app.on_action("transcribe.file", name="Transcribe", description="Transcribe file")
    async def handler(event: ActionEvent):
        call_log.append(event)

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1


async def test_action_explicit_secret_takes_precedence_over_env_var(
    action_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that explicit secret parameter takes precedence over CUSTOM_ACTION_SECRET env var."""
    # Set a different secret in env var
    monkeypatch.setenv("CUSTOM_ACTION_SECRET", "env_var_secret")

    call_log = []
    app = App()

    # Explicit secret should be used, not env var
    @app.on_action("transcribe.file", name="Transcribe", description="Transcribe file", secret=sample_secret)
    async def handler(event: ActionEvent):
        call_log.append(event)

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        # Use the explicit secret for signature, not env var
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1


def test_action_raises_error_when_no_secret_provided(monkeypatch):
    """Tests that ValueError is raised when neither secret parameter nor env var is provided."""
    # Ensure env var is not set
    monkeypatch.delenv("CUSTOM_ACTION_SECRET", raising=False)

    app = App()

    # Should raise ValueError at decorator time
    with pytest.raises(
        ValueError,
        match="Custom action secret must be provided either via 'secret' parameter, app-level secret_resolver, or CUSTOM_ACTION_SECRET environment variable",
    ):

        @app.on_action("transcribe.file", name="Transcribe", description="Transcribe file")
        async def handler(event: ActionEvent):
            pass


async def test_both_webhook_and_action_work_with_separate_env_vars(
    webhook_payload, action_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that webhooks and actions can use their respective env vars simultaneously."""
    webhook_secret = "webhook_secret_123"
    action_secret = "action_secret_456"

    monkeypatch.setenv("WEBHOOK_SECRET", webhook_secret)
    monkeypatch.setenv("CUSTOM_ACTION_SECRET", action_secret)

    call_log = []
    app = App()

    @app.on_webhook("file.ready")
    async def webhook_handler(event: WebhookEvent):
        call_log.append("webhook")

    @app.on_action("transcribe.file", name="Transcribe", description="Transcribe file")
    async def action_handler(event: ActionEvent):
        call_log.append("action")

    # Test webhook with webhook secret
    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, webhook_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert "webhook" in call_log

    # Test action with action secret
    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, action_secret),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert "action" in call_log
    assert len(call_log) == 2


async def test_webhook_empty_string_secret_falls_back_to_env_var(
    webhook_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that empty string secret parameter falls back to WEBHOOK_SECRET env var."""
    # Set the environment variable
    monkeypatch.setenv("WEBHOOK_SECRET", sample_secret)

    call_log = []
    app = App()

    # Empty string should be treated as falsy and fall back to env var
    @app.on_webhook("file.ready", secret="")
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1


async def test_action_empty_string_secret_falls_back_to_env_var(
    action_payload, sample_secret, create_valid_signature, monkeypatch
):
    """Tests that empty string secret parameter falls back to CUSTOM_ACTION_SECRET env var."""
    # Set the environment variable
    monkeypatch.setenv("CUSTOM_ACTION_SECRET", sample_secret)

    call_log = []
    app = App()

    # Empty string should be treated as falsy and fall back to env var
    @app.on_action("transcribe.file", name="Transcribe", description="Transcribe file", secret="")
    async def handler(event: ActionEvent):
        call_log.append(event)

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert len(call_log) == 1


# --- Decorator-Level Resolver Tests ---


async def test_decorator_level_webhook_resolver(webhook_payload, sample_secret, create_valid_signature):
    """Tests that decorator-level resolver is called for webhook events."""
    resolver_call_log: list[WebhookEvent] = []

    async def webhook_resolver(event: WebhookEvent) -> str:
        resolver_call_log.append(event)
        return sample_secret

    call_log = []
    app = App()

    # Use decorator-level resolver
    @app.on_webhook("file.ready", secret=webhook_resolver)
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    # Verify handler was called
    assert len(call_log) == 1
    # Verify resolver was called with correct event
    assert len(resolver_call_log) == 1
    assert resolver_call_log[0].type == "file.ready"


async def test_decorator_level_action_resolver(action_payload, sample_secret, create_valid_signature):
    """Tests that decorator-level resolver is called for action events."""
    resolver_call_log: list[ActionEvent] = []

    async def action_resolver(event: ActionEvent) -> str:
        resolver_call_log.append(event)
        return sample_secret

    call_log = []
    app = App()

    # Use decorator-level resolver
    @app.on_action("transcribe.file", name="Transcribe", description="Transcribe file", secret=action_resolver)
    async def handler(event: ActionEvent):
        call_log.append(event)

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    # Verify handler was called
    assert len(call_log) == 1
    # Verify resolver was called with correct event
    assert len(resolver_call_log) == 1
    assert resolver_call_log[0].type == "transcribe.file"


async def test_resolver_returning_empty_string_fails(webhook_payload, create_valid_signature):
    """Tests that resolver returning empty string causes request to fail."""

    async def empty_resolver(event: WebhookEvent) -> str:
        return ""

    call_log = []
    app = App()

    @app.on_webhook("file.ready", secret=empty_resolver)
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, "any_secret"),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        # 503 indicates configuration/service error
        assert response.status_code == 503
        assert "Configuration error" in response.text

    # Verify handler was NOT called
    assert len(call_log) == 0


async def test_resolver_error_handling(webhook_payload, create_valid_signature):
    """Tests that errors in resolvers are handled gracefully."""

    async def failing_resolver(event: WebhookEvent) -> str:
        raise RuntimeError("Database connection failed")

    call_log = []
    app = App()

    @app.on_webhook("file.ready", secret=failing_resolver)
    async def handler(event: WebhookEvent):
        call_log.append(event)

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, "any_secret"),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        # 503 indicates configuration/service error
        assert response.status_code == 503
        assert "Configuration error" in response.text

    # Verify handler was NOT called
    assert len(call_log) == 0
