import json
import time

import httpx
import pytest

from frameio_kit.app import App
from frameio_kit.events import ActionEvent, AnyEvent, WebhookEvent
from frameio_kit.middleware import AnyResponse, Middleware, NextFunc
from frameio_kit.ui import Message

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
    payload["account_id"] = "acc_123"
    payload["action_id"] = "act_123"
    payload["interaction_id"] = "int_123"
    payload["type"] = "transcribe.file"
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
        assert "Invalid JSON payload" in response.text


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


async def test_handle_request_serializes_ui_response(action_payload, sample_secret, create_valid_signature):
    """Tests that a Message or Form returned by a handler is correctly serialized to JSON."""
    app = App()

    @app.on_action("transcribe.file", name="Transcribe", description="...", secret=sample_secret)
    async def handler(event: ActionEvent):
        return Message(title="Success", description=f"File {event.resource_id} sent.")

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
