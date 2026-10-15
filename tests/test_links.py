"""Tests for link management endpoints (/api/links)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch


def test_create_link_valid(client, auth_headers):
    """Verifies successful creation of a short link."""
    headers = auth_headers("user1@example.com")
    resp = client.post(
        "/api/links",
        json={"url": "https://python.org"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["original_url"] == "https://python.org"
    assert len(data["short_code"]) == 7
    assert data["short_url"].endswith(data["short_code"])
    assert data["is_active"] is True
    assert data["click_count"] == 0


def test_create_link_invalid_scheme(client, auth_headers):
    """Verifies rejection of non-http/https URL schemes."""
    headers = auth_headers("user1@example.com")
    resp = client.post(
        "/api/links",
        json={"url": "ftp://files.example.com/download"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "scheme must be http or https" in resp.json()["detail"]


def test_create_link_custom_alias(client, auth_headers):
    """Verifies creating a link with a valid custom alias."""
    headers = auth_headers("user1@example.com")
    resp = client.post(
        "/api/links",
        json={"url": "https://fastapi.tiangolo.com", "custom_alias": "custom-fastapi"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["short_code"] == "custom-fastapi"


def test_create_link_duplicate_alias(client, auth_headers):
    """Verifies that duplicate custom aliases return 409 Conflict."""
    headers = auth_headers("user1@example.com")
    payload = {"url": "https://fastapi.tiangolo.com", "custom_alias": "same-alias"}
    resp1 = client.post("/api/links", json=payload, headers=headers)
    assert resp1.status_code == 201

    resp2 = client.post("/api/links", json=payload, headers=headers)
    assert resp2.status_code == 409
    assert "already in use" in resp2.json()["detail"]


def test_create_link_reserved_alias(client, auth_headers):
    """Verifies rejection of reserved system words as aliases."""
    headers = auth_headers("user1@example.com")
    for reserved in ["health", "docs", "api", "auth", "admin", "login"]:
        resp = client.post(
            "/api/links",
            json={"url": "https://example.com", "custom_alias": reserved},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "reserved system keyword" in resp.json()["detail"]


def test_create_link_private_host(client, auth_headers):
    """Verifies SSRF protection against localhost and private IP addresses."""
    headers = auth_headers("user1@example.com")
    private_urls = [
        "http://localhost:8080/dashboard",
        "http://127.0.0.1:5432/admin",
        "http://192.168.1.1/router",
        "http://10.0.0.1/secret",
    ]
    for url in private_urls:
        resp = client.post("/api/links", json={"url": url}, headers=headers)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "forbidden" in detail or "own domain" in detail


def test_create_link_expired_in_past(client, auth_headers):
    """Verifies rejection of expiration timestamps in the past."""
    headers = auth_headers("user1@example.com")
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    resp = client.post(
        "/api/links",
        json={"url": "https://example.com", "expires_at": past_time},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Expiration timestamp must be in the future" in resp.json()["detail"]


def test_ownership_isolation_returns_404(client, auth_headers):
    """Verifies that User B receives 404 (never 403) when accessing User A's links."""
    headers_a = auth_headers("user_a@example.com")
    headers_b = auth_headers("user_b@example.com")

    # User A creates a link
    create_resp = client.post(
        "/api/links",
        json={"url": "https://example.com/target-a"},
        headers=headers_a,
    )
    link_id = create_resp.json()["id"]

    # User B attempts to access User A's link -> 404
    get_resp = client.get(f"/api/links/{link_id}", headers=headers_b)
    assert get_resp.status_code == 404

    # User B attempts to update User A's link -> 404
    patch_resp = client.patch(
        f"/api/links/{link_id}",
        json={"is_active": False},
        headers=headers_b,
    )
    assert patch_resp.status_code == 404

    # User B attempts to delete User A's link -> 404
    delete_resp = client.delete(f"/api/links/{link_id}", headers=headers_b)
    assert delete_resp.status_code == 404


def test_list_links_pagination(client, auth_headers):
    """Verifies pagination parameters on listing links."""
    headers = auth_headers("paginated_user@example.com")
    for i in range(5):
        client.post("/api/links", json={"url": f"https://example.com/{i}"}, headers=headers)

    resp = client.get("/api/links?page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_code_collision_retry(client, auth_headers):
    """Verifies that the link creator retries code generation when a collision occurs."""
    headers = auth_headers("retry_user@example.com")

    codes = ["COLLIDE", "COLLIDE", "SUCCESS1"]
    call_count = 0

    def mock_generate_code(length=7):
        nonlocal call_count
        res = codes[call_count]
        call_count += 1
        return res

    with patch("app.routers.links.generate_short_code", side_effect=mock_generate_code):
        # First creation succeeds with 'COLLIDE'
        resp1 = client.post("/api/links", json={"url": "https://first.com"}, headers=headers)
        assert resp1.status_code == 201
        assert resp1.json()["short_code"] == "COLLIDE"

        # Second creation generates 'COLLIDE' on attempt 1, catches collision, and succeeds with 'SUCCESS1'
        resp2 = client.post("/api/links", json={"url": "https://second.com"}, headers=headers)
        assert resp2.status_code == 201
        assert resp2.json()["short_code"] == "SUCCESS1"
