import json
import time

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from starlette.middleware import Middleware as StarletteMiddleware

from frameio_kit import ActionEvent, App, Message, WebhookEvent
from frameio_kit._otel import OpenTelemetryMiddleware


@pytest.fixture
def span_exporter():
    """In-memory span exporter for capturing spans in tests."""
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(span_exporter):
    """TracerProvider wired to an in-memory exporter."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture
def otel_middleware(tracer_provider):
    """OpenTelemetryMiddleware wired to a test tracer provider."""
    return OpenTelemetryMiddleware(tracer_provider=tracer_provider)


@pytest.fixture
def sample_secret():
    return "test_secret"


@pytest.fixture
def webhook_payload():
    return {
        "type": "file.ready",
        "account": {"id": "acc_123"},
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
    }


@pytest.fixture
def action_payload():
    return {
        "type": "transcribe.file",
        "account_id": "acc_456",
        "action_id": "act_789",
        "interaction_id": "int_012",
        "project": {"id": "proj_456"},
        "resource": {"id": "file_456", "type": "version_stack"},
        "user": {"id": "user_456"},
        "workspace": {"id": "ws_456"},
        "data": {"language": "en-US"},
    }


async def test_webhook_creates_span_with_correct_attributes(
    otel_middleware, span_exporter, webhook_payload, sample_secret, create_valid_signature
):
    app = App(middleware=[otel_middleware])

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        pass

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "frameio file.ready"
    assert span.kind == SpanKind.SERVER
    assert span.status.status_code == StatusCode.OK

    attrs = dict(span.attributes)
    assert attrs["frameio.event.type"] == "file.ready"
    assert attrs["frameio.account.id"] == "acc_123"
    assert attrs["frameio.resource.id"] == "file_123"
    assert attrs["frameio.resource.type"] == "file"
    assert attrs["frameio.user.id"] == "user_123"
    assert attrs["frameio.project.id"] == "proj_123"
    assert attrs["frameio.workspace.id"] == "ws_123"
    assert "frameio.action.id" not in attrs
    assert "frameio.interaction.id" not in attrs


async def test_action_creates_span_with_action_attributes(
    otel_middleware, span_exporter, action_payload, sample_secret, create_valid_signature
):
    app = App(middleware=[otel_middleware])

    @app.on_action("transcribe.file", name="Transcribe", description="Transcribe a file", secret=sample_secret)
    async def handler(event: ActionEvent):
        return Message(title="Done", description="Transcription complete")

    body = json.dumps(action_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "frameio transcribe.file"

    attrs = dict(span.attributes)
    assert attrs["frameio.event.type"] == "transcribe.file"
    assert attrs["frameio.account.id"] == "acc_456"
    assert attrs["frameio.resource.id"] == "file_456"
    assert attrs["frameio.resource.type"] == "version_stack"
    assert attrs["frameio.action.id"] == "act_789"
    assert attrs["frameio.interaction.id"] == "int_012"


async def test_handler_exception_records_error_on_span(
    otel_middleware, span_exporter, webhook_payload, sample_secret, create_valid_signature
):
    app = App(middleware=[otel_middleware])

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        raise RuntimeError("something went wrong")

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 500

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert "something went wrong" in span.status.description

    exception_events = [e for e in span.events if e.name == "exception"]
    assert len(exception_events) >= 1


async def test_scope_app_set_and_routes_exposed(
    otel_middleware, webhook_payload, sample_secret, create_valid_signature
):
    """Verify scope['app'] inside Starlette's middleware stack points to App.

    OpenTelemetry's Starlette instrumentation reads scope['app'].routes to
    resolve the HTTP route for span names.  Starlette's own __call__
    overwrites scope['app'] with itself, so _ScopeAppMiddleware (added by
    App._create_asgi_app) must restore it to the outer App instance before
    any instrumentation middleware runs.
    """
    app = App(middleware=[otel_middleware])
    captured_scope_app = {}

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        # Inside the request handler, request.app (i.e. scope["app"])
        # should be the outer App, not the inner Starlette.
        pass

    # Inject a thin ASGI middleware into the *inner* Starlette stack that
    # records what scope["app"] is when middleware executes.  We append
    # to user_middleware (rather than add_middleware which inserts at 0)
    # so the recorder sits *after* _ScopeAppMiddleware in the call chain
    # — the same position OTel auto-instrumentation middleware occupies.
    class _Recorder:
        def __init__(self, asgi_app):
            self.asgi_app = asgi_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                captured_scope_app["app"] = scope.get("app")
            await self.asgi_app(scope, receive, send)

    app._asgi_app.user_middleware.append(StarletteMiddleware(_Recorder))  # type: ignore[arg-type]

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200
    # scope["app"] inside Starlette's middleware stack must be the outer App.
    assert captured_scope_app["app"] is app
    # The routes property must proxy to the inner Starlette routes.
    assert app.routes is app._asgi_app.routes
    # The state property must proxy to the inner Starlette state.
    assert app.state is app._asgi_app.state


async def test_custom_tracer_name(
    span_exporter, tracer_provider, webhook_payload, sample_secret, create_valid_signature
):
    middleware = OpenTelemetryMiddleware(tracer_name="my_custom_tracer", tracer_provider=tracer_provider)
    app = App(middleware=[middleware])

    @app.on_webhook("file.ready", secret=sample_secret)
    async def handler(event: WebhookEvent):
        pass

    body = json.dumps(webhook_payload).encode()
    ts = int(time.time())
    headers = {
        "X-Frameio-Request-Timestamp": str(ts),
        "X-Frameio-Signature": create_valid_signature(ts, body, sample_secret),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/", content=body, headers=headers)

    assert response.status_code == 200

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].instrumentation_scope.name == "my_custom_tracer"
