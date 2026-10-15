"""Tests for authentication endpoints (/auth/register and /auth/login)."""



def test_register_success(client):
    """Verifies that a new user can register successfully."""
    resp = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "securepassword123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert "id" in data


def test_register_duplicate_email(client):
    """Verifies that registering an existing email returns 409 Conflict."""
    payload = {"email": "duplicate@example.com", "password": "securepassword123"}
    resp1 = client.post("/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/auth/register", json=payload)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]


def test_register_bad_password(client):
    """Verifies that passwords under 8 characters are rejected with 422."""
    resp = client.post(
        "/auth/register",
        json={"email": "shortpw@example.com", "password": "short"},
    )
    assert resp.status_code == 422


def test_login_success(client):
    """Verifies that a registered user can log in and receive a valid JWT token."""
    email = "bob@example.com"
    password = "mypassword123"
    client.post("/auth/register", json={"email": email, "password": password})

    resp = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_bad_password(client):
    """Verifies that incorrect passwords return 401 Unauthorized."""
    email = "charlie@example.com"
    client.post("/auth/register", json={"email": email, "password": "correctpassword123"})

    resp = client.post(
        "/auth/login",
        data={"username": email, "password": "wrongpassword123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 401
    assert "Incorrect email or password" in resp.json()["detail"]


def test_login_nonexistent_email(client):
    """Verifies that non-existent accounts return 401 Unauthorized."""
    resp = client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "somepassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 401
