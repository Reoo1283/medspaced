from fastapi.testclient import TestClient

from app.core.config import settings


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient):
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "medspaced_http_requests_total" in body
    assert 'method="GET"' in body
    assert "medspaced_http_request_duration_seconds_count" in body


def test_metrics_token_protects_endpoint(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "gizli")
    assert client.get("/metrics").status_code == 401
    allowed = client.get("/metrics", headers={"Authorization": "Bearer gizli"})
    assert allowed.status_code == 200
