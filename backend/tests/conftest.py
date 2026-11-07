import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.environ["MEDSPACED_DATABASE_URL"] = f"sqlite:///{BASE / 'var' / 'test_medspaced.db'}"
os.environ["MEDSPACED_STORAGE_DIR"] = str(BASE / "var" / "test_storage")
os.environ["MEDSPACED_LLM_PROVIDER"] = "fake"
os.environ["MEDSPACED_SECRET_KEY"] = "test-secret-key"
os.environ["MEDSPACED_ENVIRONMENT"] = "test"
os.environ["MEDSPACED_RATE_LIMIT_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from app import models
from app.core.db import SessionLocal, engine
from app.main import app


@pytest.fixture()
def client():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register(
    client: TestClient,
    *,
    email: str = "student@example.com",
    password: str = "password123",
    full_name: str = "Test Kullanıcı",
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


def make_reviewer(client: TestClient, db, email: str = "reviewer@example.com") -> dict:
    data = register(client, email=email, full_name="Uzman")
    user = db.get(models.User, data["user"]["id"])
    user.role = "reviewer"
    db.commit()
    return data


@pytest.fixture()
def student(client):
    return register(client)


@pytest.fixture()
def reviewer(client, db):
    return make_reviewer(client, db)
