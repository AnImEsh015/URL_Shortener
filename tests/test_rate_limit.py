"""Tests for sliding-window rate limiting and fail-open resilience."""

from unittest.mock import patch

from app.config import settings
from app.services.rate_limit import check_rate_limit


def test_rate_limit_exceeded_returns_429(client):
    """Verifies that exceeding the configured request threshold returns HTTP 429 with Retry-After."""
    limit = settings.RATE_LIMIT_LOGIN_PER_MIN

    # Make allowed number of requests
    for _ in range(limit):
        client.post(
            "/auth/login",
            data={"username": "test@example.com", "password": "wrong"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    # (Limit + 1)-th request should trigger 429
    resp = client.post(
        "/auth/login",
        data={"username": "test@example.com", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


def test_rate_limit_fail_open_on_redis_error():
    """Verifies that check_rate_limit allows requests when Redis raises an error."""
    with patch("app.services.rate_limit.get_redis_client", side_effect=Exception("Redis connection timed out")):
        # Should not raise HTTPException or crash
        check_rate_limit("test:ip:1.2.3.4", limit=5, window_seconds=60)
