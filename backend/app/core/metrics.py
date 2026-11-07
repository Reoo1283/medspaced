from __future__ import annotations

import threading

_lock = threading.Lock()
_requests: dict[tuple[str, int], int] = {}
_duration_sum = 0.0
_duration_count = 0
_in_flight = 0


def request_started() -> None:
    global _in_flight
    with _lock:
        _in_flight += 1


def request_finished(method: str, status_code: int, duration_seconds: float) -> None:
    global _duration_sum, _duration_count, _in_flight
    with _lock:
        key = (method, status_code)
        _requests[key] = _requests.get(key, 0) + 1
        _duration_sum += duration_seconds
        _duration_count += 1
        _in_flight = max(0, _in_flight - 1)


def render() -> str:
    with _lock:
        requests = sorted(_requests.items())
        duration_sum = _duration_sum
        duration_count = _duration_count
        in_flight = _in_flight
    lines = [
        "# HELP medspaced_http_requests_total Toplam HTTP isteği.",
        "# TYPE medspaced_http_requests_total counter",
    ]
    for (method, status_code), count in requests:
        lines.append(
            f'medspaced_http_requests_total{{method="{method}",status="{status_code}"}} {count}'
        )
    lines += [
        "# HELP medspaced_http_request_duration_seconds HTTP istek süresi.",
        "# TYPE medspaced_http_request_duration_seconds summary",
        f"medspaced_http_request_duration_seconds_sum {duration_sum:.6f}",
        f"medspaced_http_request_duration_seconds_count {duration_count}",
        "# HELP medspaced_http_requests_in_flight Şu anda işlenen istek sayısı.",
        "# TYPE medspaced_http_requests_in_flight gauge",
        f"medspaced_http_requests_in_flight {in_flight}",
        "",
    ]
    return "\n".join(lines)
