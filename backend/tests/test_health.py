from fastapi.testclient import TestClient

from app.core.config import Settings, validate_runtime_settings


def test_health_and_readiness_include_security_headers(client: TestClient):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["X-Request-ID"]

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "database": "ok"}


def test_request_id_is_preserved_when_valid(client: TestClient):
    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_production_rejects_weak_secret():
    config = Settings(environment="production", secret_key="dev-only-secret-change-in-production")
    try:
        validate_runtime_settings(config)
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
    else:
        raise AssertionError("zayıf üretim anahtarı reddedilmedi")
