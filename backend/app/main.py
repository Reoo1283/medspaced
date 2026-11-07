import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import settings, validate_runtime_settings
from app.core.db import SessionLocal, init_db
from app.core import metrics
from app.core.log_config import configure_logging
from app.core.observability import request_context_middleware
from app.core.rate_limit import RateLimitMiddleware, build_rate_limiter
from app.core.telemetry import configure_error_reporting, configure_telemetry, reset_telemetry


rate_limiter = build_rate_limiter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    validate_runtime_settings()
    configure_error_reporting()
    configure_telemetry()
    init_db()
    try:
        yield
    finally:
        reset_telemetry()
        await rate_limiter.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Anestezi öğrencileri için aralıklı tekrar platformu",
    lifespan=lifespan,
)

app.add_middleware(
    RateLimitMiddleware,
    limiter=rate_limiter,
    enabled=settings.rate_limit_enabled,
    auth_limit=settings.auth_rate_limit_per_minute,
    global_limit=settings.rate_limit_per_minute,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_context_middleware)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint(request: Request) -> PlainTextResponse:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Bulunamadı")
    if settings.metrics_token:
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.metrics_token}"
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="Yetkisiz")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


@app.get("/ready", tags=["system"])
def ready() -> dict:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Veritabanı hazır değil") from exc
    finally:
        db.close()
    return {"status": "ready", "database": "ok"}
