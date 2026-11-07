import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import observability, telemetry


def test_error_reporting_noop_without_dsn(monkeypatch):
    called = []
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: called.append(kwargs))
    assert telemetry.configure_error_reporting("") is False
    assert called == []


def test_error_reporting_initializes_with_dsn(monkeypatch):
    called = []
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: called.append(kwargs))
    assert telemetry.configure_error_reporting("https://public@example.invalid/1") is True
    assert called and called[0]["dsn"] == "https://public@example.invalid/1"
    assert called[0]["send_default_pii"] is False


def test_tracing_middleware_records_span():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = telemetry.configure_telemetry(exporter=exporter)
    assert provider is not None
    try:
        app = FastAPI()

        @app.get("/ping")
        def ping():
            return {"ok": True}

        with TestClient(app) as client:
            assert client.get("/ping", headers={"X-Request-ID": "trace-test"}).status_code == 200
        provider.force_flush()
        spans = exporter.get_finished_spans()
        server_span = next(
            span
            for span in spans
            if span.name == "GET /ping" and "server.address" in span.attributes
        )
        assert server_span.attributes["http.response.status_code"] == 200
        assert server_span.attributes["url.path"] == "/ping"
    finally:
        telemetry.reset_telemetry()


def test_unhandled_exception_is_captured(monkeypatch):
    captured = []
    monkeypatch.setattr(observability, "capture_exception", lambda exc, request_id=None: captured.append(request_id))
    app = FastAPI()
    app.middleware("http")(observability.request_context_middleware)

    @app.get("/boom")
    def boom():
        raise RuntimeError("patladı")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert captured == [response.headers["X-Request-ID"]]
