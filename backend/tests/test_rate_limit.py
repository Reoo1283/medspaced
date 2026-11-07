import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.log_config import JsonFormatter, request_id_var
from app.core.rate_limit import RateLimiter, RateLimitMiddleware


def _limited_app(*, auth_limit: int = 2, global_limit: int = 100, client=("testclient", 50000)) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(),
        enabled=True,
        auth_limit=auth_limit,
        global_limit=global_limit,
    )

    @app.post("/api/v1/auth/login")
    def login() -> dict:
        return {"ok": True}

    @app.get("/api/v1/items")
    def items() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return TestClient(app, client=client)


def test_auth_rate_limit_returns_429_with_retry_after():
    client = _limited_app(auth_limit=2)
    assert client.post("/api/v1/auth/login").status_code == 200
    assert client.post("/api/v1/auth/login").status_code == 200
    blocked = client.post("/api/v1/auth/login")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
    assert "bekleyin" in blocked.json()["detail"]
    assert client.get("/health").status_code == 200


def test_global_rate_limit_applies_to_api_routes():
    client = _limited_app(global_limit=2)
    assert client.get("/api/v1/items").status_code == 200
    assert client.get("/api/v1/items").status_code == 200
    assert client.get("/api/v1/items").status_code == 429


def test_rate_limiter_window_resets():
    limiter = RateLimiter()
    assert limiter.allow("client", limit=1, now=100.0)[0] is True
    assert limiter.allow("client", limit=1, now=101.0)[0] is False
    assert limiter.allow("client", limit=1, now=161.0)[0] is True


def test_json_formatter_includes_request_id():
    token = request_id_var.set("req-123")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "merhaba", None, None)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-123"
    assert payload["message"] == "merhaba"
    assert payload["level"] == "INFO"


def test_redis_rate_limiter_shares_window_counter():
    import asyncio

    from fakeredis.aioredis import FakeRedis

    from app.core.rate_limit import RedisRateLimiter

    async def run():
        limiter = RedisRateLimiter("redis://unused", client=FakeRedis(decode_responses=True))
        first = await limiter.allow("client", limit=1, now=100.0)
        second = await limiter.allow("client", limit=1, now=101.0)
        later = await limiter.allow("client", limit=1, now=161.0)
        await limiter.close()
        return first[0], second[0], later[0]

    assert asyncio.run(run()) == (True, False, True)


def test_redis_rate_limiter_falls_back_when_redis_fails():
    import asyncio

    from app.core.rate_limit import RedisRateLimiter

    class BrokenRedis:
        async def incr(self, key):
            raise ConnectionError("redis yok")

    async def run():
        limiter = RedisRateLimiter("redis://unused", client=BrokenRedis())
        return await limiter.allow("client", limit=1, now=100.0), await limiter.allow(
            "client", limit=1, now=101.0
        )

    first, second = asyncio.run(run())
    assert first[0] is True
    assert second[0] is False


def test_trusted_proxy_header_is_used_for_rate_limit_identity(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1/32")
    client = _limited_app(auth_limit=1, client=("127.0.0.1", 50000))
    assert client.post("/api/v1/auth/login", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.post("/api/v1/auth/login", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert client.post("/api/v1/auth/login", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
