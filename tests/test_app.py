import json
import time

import httpx
import pytest

from frameio_kit.app import App
from frameio_kit.events import ActionEvent, WebhookEvent
from frameio_kit.ui import Message


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
