import json
import time

import httpx
import pytest

from frameio_kit import ActionEvent, App, Message


@pytest.fixture
def sample_secret():
    return "test_secret"


def _make_action_payload(*, resource_type: str = "file", event_type: str = "my_app.transcribe") -> dict:
    return {
        "type": event_type,
        "account_id": "acc_123",
        "project": {"id": "proj_123"},
        "resource": {"id": "res_123", "type": resource_type},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
        "action_id": "act_123",
        "interaction_id": "int_123",
    }


async def test_resource_type_file_accepts_file_event(sample_secret, create_valid_signature):
    """Action with resource_type='file' should call handler for file events."""
    call_log = []
    app = App()

    @app.on_action(
        "my_app.transcribe",
        name="Transcribe",
        description="Transcribe this file",
        secret=sample_secret,
        resource_type="file",
    )
    async def handler(event: ActionEvent):
        call_log.append(event)
        return Message(title="Done", description="Transcribed.")

    payload = _make_action_payload(resource_type="file")
    body = json.dumps(payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["title"] == "Done"
    assert len(call_log) == 1


async def test_resource_type_file_rejects_folder_event(sample_secret, create_valid_signature):
    """Action with resource_type='file' should return 'Action Not Available' for folder events."""
    call_log = []
    app = App()

    @app.on_action(
        "my_app.transcribe",
        name="Transcribe",
        description="Transcribe this file",
        secret=sample_secret,
        resource_type="file",
    )
    async def handler(event: ActionEvent):
        call_log.append(event)
        return Message(title="Done", description="Transcribed.")

    payload = _make_action_payload(resource_type="folder")
    body = json.dumps(payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Action Not Available"
    assert "file" in data["description"]
    # Handler should NOT have been called
    assert len(call_log) == 0


async def test_resource_type_list_accepts_matching_types(sample_secret, create_valid_signature):
    """Action with resource_type=['file', 'version_stack'] should accept both types."""
    call_log = []
    app = App()

    @app.on_action(
        "my_app.analyze",
        name="Analyze",
        description="Analyze this asset",
        secret=sample_secret,
        resource_type=["file", "version_stack"],
    )
    async def handler(event: ActionEvent):
        call_log.append(event)
        return Message(title="Done", description="Analyzed.")

    for rt in ["file", "version_stack"]:
        payload = _make_action_payload(resource_type=rt, event_type="my_app.analyze")
        body = json.dumps(payload).encode()
        ts = int(time.time())
        headers = {
            "X-Frameio-Request-Timestamp": str(ts),
            "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
        }

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            response = await client.post("/", content=body, headers=headers)

        assert response.status_code == 200
        assert response.json()["title"] == "Done"

    assert len(call_log) == 2


async def test_resource_type_list_rejects_non_matching_type(sample_secret, create_valid_signature):
    """Action with resource_type=['file', 'version_stack'] should reject folder."""
    call_log = []
    app = App()

    @app.on_action(
        "my_app.analyze",
        name="Analyze",
        description="Analyze this asset",
        secret=sample_secret,
        resource_type=["file", "version_stack"],
    )
    async def handler(event: ActionEvent):
        call_log.append(event)
        return Message(title="Done", description="Analyzed.")

    payload = _make_action_payload(resource_type="folder", event_type="my_app.analyze")
    body = json.dumps(payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Action Not Available"
    assert "file" in data["description"]
    assert "version_stack" in data["description"]
    assert len(call_log) == 0


async def test_no_resource_type_accepts_all(sample_secret, create_valid_signature):
    """Action with no resource_type should accept all resource types."""
    call_log = []
    app = App()

    @app.on_action(
        "my_app.notify",
        name="Notify",
        description="Notify about this asset",
        secret=sample_secret,
    )
    async def handler(event: ActionEvent):
        call_log.append(event)
        return Message(title="Done", description="Notified.")

    for rt in ["file", "folder", "version_stack"]:
        payload = _make_action_payload(resource_type=rt, event_type="my_app.notify")
        body = json.dumps(payload).encode()
        ts = int(time.time())
        headers = {
            "X-Frameio-Request-Timestamp": str(ts),
            "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
        }

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            response = await client.post("/", content=body, headers=headers)

        assert response.status_code == 200
        assert response.json()["title"] == "Done"

    assert len(call_log) == 3


def test_empty_resource_type_list_raises_error(sample_secret):
    """Passing resource_type=[] should raise ValueError at decorator time."""
    app = App()

    with pytest.raises(ValueError, match="resource_type must not be an empty sequence"):

        @app.on_action(
            "my_app.bad",
            name="Bad",
            description="Bad action",
            secret=sample_secret,
            resource_type=[],
        )
        async def handler(event: ActionEvent):
            pass


def test_validate_configuration_catches_invalid_resource_type(sample_secret, monkeypatch):
    """validate_configuration() should report invalid resource type strings."""
    monkeypatch.setenv("CUSTOM_ACTION_SECRET", sample_secret)
    app = App()

    @app.on_action(
        "my_app.bad",
        name="Bad",
        description="Bad action",
        resource_type="invalid",  # type: ignore[arg-type]
    )
    async def handler(event: ActionEvent):
        pass

    errors = app.validate_configuration()
    assert len(errors) == 1
    assert "invalid resource type" in errors[0].lower()
    assert "invalid" in errors[0]


def test_validate_configuration_passes_for_valid_resource_types(sample_secret, monkeypatch):
    """validate_configuration() should return no errors for valid resource types."""
    monkeypatch.setenv("CUSTOM_ACTION_SECRET", sample_secret)
    app = App()

    @app.on_action(
        "my_app.good",
        name="Good",
        description="Good action",
        resource_type=["file", "folder"],
    )
    async def handler(event: ActionEvent):
        pass

    errors = app.validate_configuration()
    assert errors == []
