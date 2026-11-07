from __future__ import annotations

import asyncio
import inspect
import ipaddress
import logging
import threading
import time
from typing import Any, Protocol

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class Limiter(Protocol):
    def allow(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int = 60,
        now: float | None = None,
    ) -> tuple[bool, int] | Any: ...

    async def close(self) -> None: ...


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def allow(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int = 60,
        now: float | None = None,
    ) -> tuple[bool, int]:
        if limit <= 0:
            return True, 0
        current = now if now is not None else time.monotonic()
        window = int(current // window_seconds)
        retry_after = max(1, int(window_seconds - (current % window_seconds)))
        with self._lock:
            stored_window, count = self._buckets.get(key, (window, 0))
            if stored_window != window:
                stored_window, count = window, 0
            count += 1
            self._buckets[key] = (stored_window, count)
            if len(self._buckets) > 10000:
                self._buckets = {
                    name: value for name, value in self._buckets.items() if value[0] == window
                }
            return count <= limit, retry_after

    async def close(self) -> None:
        return None


class RedisRateLimiter:
    def __init__(
        self,
        redis_url: str,
        *,
        prefix: str = "medspaced:ratelimit",
        fallback: RateLimiter | None = None,
        client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.fallback = fallback or RateLimiter()
        self._client = client
        self._warned = False

    def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def allow(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int = 60,
        now: float | None = None,
    ) -> tuple[bool, int]:
        if limit <= 0:
            return True, 0
        current = now if now is not None else time.time()
        bucket = int(current // window_seconds)
        retry_after = max(1, int(window_seconds - (current % window_seconds)))
        redis_key = f"{self.prefix}:{key}:{bucket}"
        try:
            client = self._get_client()
            count = await client.incr(redis_key)
            if count == 1:
                await client.expire(redis_key, window_seconds + 1)
            if count > limit:
                ttl = await client.ttl(redis_key)
                return False, max(1, ttl if ttl and ttl > 0 else retry_after)
            return True, retry_after
        except Exception as exc:
            if not self._warned:
                logger.warning("Redis rate limiter kullanılamıyor, belleğe düşülüyor: %s", exc)
                self._warned = True
            return self.fallback.allow(
                key,
                limit=limit,
                window_seconds=window_seconds,
                now=time.monotonic(),
            )

    async def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result


def build_rate_limiter() -> Limiter:
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter(settings.redis_url)
    return RateLimiter()


def _trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for value in settings.trusted_proxies.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.warning("Geçersiz güvenilir proxy adresi: %s", value)
    return networks


def client_identity(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if not settings.trust_proxy_headers:
        return peer
    networks = _trusted_networks()
    if not networks:
        return peer
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_address in network for network in networks):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if not hops:
        return peer
    for hop in reversed(hops):
        try:
            candidate = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not any(candidate in network for network in networks):
            return hop
    return hops[0]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limiter: Limiter | None = None,
        enabled: bool = True,
        auth_limit: int = 10,
        global_limit: int = 120,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter or RateLimiter()
        self.enabled = enabled
        self.auth_limit = auth_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds
        self.api_prefix = settings.api_prefix

    async def dispatch(self, request: Request, call_next):
        if (
            not self.enabled
            or request.method == "OPTIONS"
            or not request.url.path.startswith(self.api_prefix)
        ):
            return await call_next(request)
        client = client_identity(request)
        is_auth = request.url.path.startswith(f"{self.api_prefix}/auth")
        checks = [("auth", self.auth_limit)] if is_auth else []
        checks.append(("global", self.global_limit))
        for scope, limit in checks:
            result = self.limiter.allow(
                f"{scope}:{client}",
                limit=limit,
                window_seconds=self.window_seconds,
            )
            if inspect.isawaitable(result):
                result = await result
            allowed, retry_after = result
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Çok fazla istek gönderildi, lütfen bekleyin"},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)
