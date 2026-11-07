from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_tracer: Any = None
_provider: Any = None


def configure_error_reporting(dsn: str | None = None) -> bool:
    dsn = settings.sentry_dsn if dsn is None else dsn
    if not dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.environment,
            release=settings.app_version,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
        )
    except Exception as exc:
        logger.warning("Sentry başlatılamadı: %s", exc)
        return False
    return True


def capture_exception(exc: BaseException, *, request_id: str | None = None) -> None:
    try:
        import sentry_sdk

        if sentry_sdk.get_client().dsn is None:
            return
        with sentry_sdk.new_scope() as scope:
            if request_id:
                scope.set_tag("request_id", request_id)
            scope.capture_exception(exc)
    except Exception:
        return


def configure_telemetry(*, exporter: Any | None = None) -> Any:
    global _tracer, _provider
    if exporter is None and not (settings.otel_enabled and settings.otel_exporter_otlp_endpoint):
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        if exporter is None:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
        _tracer = provider.get_tracer("medspaced.http")
        return provider
    except Exception as exc:
        logger.warning("OpenTelemetry başlatılamadı: %s", exc)
        return None


def reset_telemetry() -> None:
    global _tracer, _provider
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:
            pass
    _tracer = None
    _provider = None
