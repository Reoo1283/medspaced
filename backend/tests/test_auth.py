from tests.conftest import register


def test_register_login_and_me(client):
    data = register(client)
    assert data["user"]["role"] == "student"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "student@example.com"


def test_duplicate_registration_rejected(client):
    register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "student@example.com",
            "password": "password123",
            "full_name": "Kopya",
        },
    )
    assert response.status_code == 409


def test_wrong_password_rejected(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_refresh_token(client):
    data = register(client)
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_student_cannot_create_skill(client, student):
    response = client.post(
        "/api/v1/skills",
        json={"title": "Yetki Testi"},
        headers=student["headers"],
    )
    assert response.status_code == 403
