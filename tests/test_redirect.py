"""Tests for short code redirection, cache-aside behavior, negative caching, and 410 states."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models import Link
from app.services.cache import get_cached_link, get_redis_client


def test_redirect_success_and_cache_aside(client, auth_headers):
    """Verifies that a valid short code redirects with 302 and populates the Redis cache."""
    headers = auth_headers("redirect_user@example.com")
    create_resp = client.post(
        "/api/links",
        json={"url": "https://docs.python.org", "custom_alias": "pydocs"},
        headers=headers,
    )
    assert create_resp.status_code == 201

    # First request: cache miss -> queries DB and populates cache
    resp = client.get("/pydocs", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://docs.python.org"

    # Verify key was stored in Redis
    cached = get_cached_link("pydocs")
    assert cached is not None
    assert cached["url"] == "https://docs.python.org"

    # Second request: served from cache
    resp2 = client.get("/pydocs", follow_redirects=False)
    assert resp2.status_code == 302
    assert resp2.headers["location"] == "https://docs.python.org"


def test_redirect_negative_caching_on_404(client):
    """Verifies that non-existent short codes return 404 and are cached negatively in Redis."""
    resp = client.get("/nonexistent-code", follow_redirects=False)
    assert resp.status_code == 404

    # Verify negative cache entry exists in Redis
    cached = get_cached_link("nonexistent-code")
    assert cached is not None
    assert cached.get("status") == "not_found"

    # Subsequent request returns 404 immediately from Redis
    resp2 = client.get("/nonexistent-code", follow_redirects=False)
    assert resp2.status_code == 404


def test_redirect_deactivated_link_returns_410(client, auth_headers):
    """Verifies that deactivated links return 410 Gone."""
    headers = auth_headers("deact_user@example.com")
    create_resp = client.post(
        "/api/links",
        json={"url": "https://example.com/inactive", "custom_alias": "inactive-link"},
        headers=headers,
    )
    link_id = create_resp.json()["id"]

    # Deactivate link
    client.patch(f"/api/links/{link_id}", json={"is_active": False}, headers=headers)

    # Redirect attempt should return 410
    resp = client.get("/inactive-link", follow_redirects=False)
    assert resp.status_code == 410
    assert "deactivated" in resp.json()["detail"]


def test_redirect_expired_link_returns_410(client, auth_headers, db):
    """Verifies that expired links return 410 Gone."""
    headers = auth_headers("exp_user@example.com")
    future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    create_resp = client.post(
        "/api/links",
        json={"url": "https://example.com/expired", "custom_alias": "exp-link", "expires_at": future_time},
        headers=headers,
    )
    link_id = create_resp.json()["id"]

    # Manually update expiration timestamp into the past in DB
    past_time = datetime.now(UTC) - timedelta(minutes=5)
    db_link = db.get(Link, link_id)
    db_link.expires_at = past_time
    db.commit()

    # Clear cache to force re-read
    r = get_redis_client()
    r.delete("link:exp-link")

    resp = client.get("/exp-link", follow_redirects=False)
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"]


def test_redirect_max_clicks_returns_410(client, auth_headers):
    """Verifies that reaching max_clicks triggers 410 Gone."""
    headers = auth_headers("clicks_user@example.com")
    create_resp = client.post(
        "/api/links",
        json={"url": "https://example.com/limit", "custom_alias": "limit-link", "max_clicks": 2},
        headers=headers,
    )
    assert create_resp.status_code == 201

    # Click 1: OK
    r1 = client.get("/limit-link", follow_redirects=False)
    assert r1.status_code == 302

    # Click 2: OK
    r2 = client.get("/limit-link", follow_redirects=False)
    assert r2.status_code == 302

    # Click 3: Exceeded -> 410
    r3 = client.get("/limit-link", follow_redirects=False)
    assert r3.status_code == 410
    assert "maximum click limit" in r3.json()["detail"]


def test_cache_invalidation_on_patch_and_delete(client, auth_headers):
    """Verifies that PATCH and DELETE operations invalidate the Redis cache entry."""
    headers = auth_headers("inval_user@example.com")
    create_resp = client.post(
        "/api/links",
        json={"url": "https://example.com/original", "custom_alias": "inval-link"},
        headers=headers,
    )
    link_id = create_resp.json()["id"]

    # Prime cache
    client.get("/inval-link", follow_redirects=False)
    assert get_cached_link("inval-link") is not None

    # Patch -> cache should be removed
    client.patch(f"/api/links/{link_id}", json={"max_clicks": 50}, headers=headers)
    assert get_cached_link("inval-link") is None

    # Re-prime cache
    client.get("/inval-link", follow_redirects=False)
    assert get_cached_link("inval-link") is not None

    # Delete -> cache should be removed
    client.delete(f"/api/links/{link_id}", headers=headers)
    assert get_cached_link("inval-link") is None


def test_redirect_celery_fail_open(client, auth_headers):
    """Verifies that if Celery enqueueing fails, the 302 redirect still succeeds."""
    headers = auth_headers("failopen_user@example.com")
    client.post(
        "/api/links",
        json={"url": "https://resilient.org", "custom_alias": "resilient"},
        headers=headers,
    )

    with patch("app.routers.redirect.record_click.delay", side_effect=Exception("Broker is down!")):
        resp = client.get("/resilient", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://resilient.org"
