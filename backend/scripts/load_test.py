from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from collections.abc import Sequence

import httpx

DEFAULT_ENDPOINTS = "/api/v1/study/stats,/api/v1/study/due,/api/v1/auth/me"
DEFAULT_P95_MS = 500.0
DEFAULT_MAX_ERROR_RATE = 0.01


def percentile(values: Sequence[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percent / 100 * len(ordered)) - 1))
    return ordered[index]


async def _worker(
    client: httpx.AsyncClient,
    token: str,
    endpoints: Sequence[str],
    deadline: float,
    stats: dict,
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    while time.perf_counter() < deadline:
        endpoint = random.choice(endpoints)
        started = time.perf_counter()
        stats["attempts"] += 1
        try:
            response = await client.get(endpoint, headers=headers)
            stats["latencies"].append((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                stats["errors"].append(f"{endpoint}:{response.status_code}")
            else:
                stats["successes"] += 1
        except Exception as exc:
            stats["errors"].append(f"{endpoint}:{type(exc).__name__}")


async def run_load(
    *,
    base_url: str,
    email: str,
    password: str,
    concurrency: int,
    duration_seconds: float,
    endpoints: Sequence[str],
    timeout_seconds: float = 10.0,
) -> dict:
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        stats = {"attempts": 0, "successes": 0, "latencies": [], "errors": []}
        deadline = time.perf_counter() + duration_seconds
        await asyncio.gather(
            *(
                _worker(client, token, endpoints, deadline, stats)
                for _ in range(concurrency)
            )
        )
    total = stats["attempts"]
    errors = stats["errors"]
    latencies = stats["latencies"]
    return {
        "base_url": base_url,
        "concurrency": concurrency,
        "duration_seconds": duration_seconds,
        "requests": total,
        "successful": stats["successes"],
        "errors": len(errors),
        "error_rate": len(errors) / total if total else 0.0,
        "requests_per_second": total / duration_seconds if duration_seconds else 0.0,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "p99_ms": percentile(latencies, 99),
        "error_samples": errors[:10],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MedSpaced HTTP capacity smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="student@medspaced.local")
    parser.add_argument("--password", default="Student1234!")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--endpoints", default=DEFAULT_ENDPOINTS)
    parser.add_argument("--p95-ms", type=float, default=DEFAULT_P95_MS)
    parser.add_argument("--max-error-rate", type=float, default=DEFAULT_MAX_ERROR_RATE)
    args = parser.parse_args(argv)
    endpoints = [item.strip() for item in args.endpoints.split(",") if item.strip()]
    summary = asyncio.run(
        run_load(
            base_url=args.base_url,
            email=args.email,
            password=args.password,
            concurrency=args.concurrency,
            duration_seconds=args.duration,
            endpoints=endpoints,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    p95 = summary["p95_ms"]
    if summary["error_rate"] > args.max_error_rate:
        return 1
    if p95 is None or p95 > args.p95_ms:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
