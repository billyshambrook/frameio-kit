"""Tests for get_request() context variable."""

import json
import time
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import Request

from frameio_kit import App, WebhookEvent, get_request
from frameio_kit._context import _request_context

SECRET = "test_secret"


class TestGetRequest:
    def test_raises_outside_context(self):
        with pytest.raises(RuntimeError, match="can only be called within a webhook or action handler"):
            get_request()

    def test_returns_value_when_set(self):
        mock_request = MagicMock(spec=Request)
        token = _request_context.set(mock_request)
        try:
            assert get_request() is mock_request
        finally:
            _request_context.reset(token)


async def test_get_request_available_in_webhook_handler(create_valid_signature):
    """Integration test: get_request() returns a valid Request inside a handler."""
    captured = {}

    app = App()

    @app.on_webhook("file.ready", secret=SECRET)
    async def on_file_ready(event: WebhookEvent):
        request = get_request()
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["custom_header"] = request.headers.get("x-custom-header")

    payload = {
        "type": "file.ready",
        "account": {"id": "acc_123"},
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
    }
    body = json.dumps(payload).encode()
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, SECRET),
        "X-Custom-Header": "test-value",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    assert captured["url"] == "http://test/"
    assert captured["method"] == "POST"
    assert captured["custom_header"] == "test-value"


async def test_get_request_reset_after_handler(create_valid_signature):
    """The request context is reset after the handler completes."""
    app = App()

    @app.on_webhook("file.ready", secret=SECRET)
    async def on_file_ready(event: WebhookEvent):
        get_request()  # should not raise

    payload = {
        "type": "file.ready",
        "account": {"id": "acc_123"},
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
    }
    body = json.dumps(payload).encode()
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, SECRET),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)
        assert response.status_code == 200

    # After the request completes, context should be reset
    with pytest.raises(RuntimeError):
        get_request()
