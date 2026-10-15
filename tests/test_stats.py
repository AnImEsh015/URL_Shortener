"""Tests for analytics, stats endpoints, and QR code generation."""

import hashlib
import hmac

from app.config import settings
from app.services.analytics import hash_client_ip


def test_ip_hashing_never_stores_raw_ip():
    """Verifies HMAC-SHA256 privacy hashing logic for client IP addresses."""
    raw_ip = "203.0.113.195"
    digest = hash_client_ip(raw_ip)
    assert len(digest) == 64
    assert raw_ip not in digest

    # Verify deterministic output with same salt
    expected = hmac.new(
        settings.IP_HASH_SALT.encode("utf-8"),
        raw_ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert digest == expected


def test_click_recording_and_stats(client, auth_headers, db):
    """Verifies background click processing and analytics aggregation endpoints."""
    headers = auth_headers("stats_owner@example.com")
    create_resp = client.post(
        "/api/links",
        json={"url": "https://fastapi.tiangolo.com", "custom_alias": "stat-link"},
        headers=headers,
    )
    link_id = create_resp.json()["id"]

    # Trigger clicks via redirect (Celery runs synchronously via task_always_eager)
    client.get(
        "/stat-link",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://news.ycombinator.com",
        },
        follow_redirects=False,
    )
    client.get(
        "/stat-link",
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148 Safari/604.1",
            "Referer": "https://google.com",
        },
        follow_redirects=False,
    )

    # 1. Summary stats
    stats_resp = client.get(f"/api/links/{link_id}/stats", headers=headers)
    assert stats_resp.status_code == 200
    summary = stats_resp.json()
    assert summary["total_clicks"] == 2
    assert summary["unique_visitors"] >= 1
    assert summary["first_click_at"] is not None
    assert summary["last_click_at"] is not None

    # 2. Timeseries stats
    ts_resp = client.get(f"/api/links/{link_id}/stats/timeseries?interval=day&days=7", headers=headers)
    assert ts_resp.status_code == 200
    ts_data = ts_resp.json()
    assert len(ts_data) >= 1
    assert ts_data[0]["clicks"] == 2

    # 3. Categorical breakdown
    breakdown_resp = client.get(f"/api/links/{link_id}/stats/breakdown?by=browser&limit=5", headers=headers)
    assert breakdown_resp.status_code == 200
    breakdown_data = breakdown_resp.json()
    assert len(breakdown_data) >= 1

    # 4. QR code endpoint
    qr_resp = client.get(f"/api/links/{link_id}/qr", headers=headers)
    assert qr_resp.status_code == 200
    assert qr_resp.headers["content-type"] == "image/png"
    assert qr_resp.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_stats_ownership_isolation(client, auth_headers):
    """Verifies that unauthorized users cannot inspect analytics (returns 404)."""
    headers_a = auth_headers("owner_a@example.com")
    headers_b = auth_headers("owner_b@example.com")

    create_resp = client.post(
        "/api/links",
        json={"url": "https://example.com/protected"},
        headers=headers_a,
    )
    link_id = create_resp.json()["id"]

    assert client.get(f"/api/links/{link_id}/stats", headers=headers_b).status_code == 404
    assert client.get(f"/api/links/{link_id}/stats/timeseries?interval=day", headers=headers_b).status_code == 404
    assert client.get(f"/api/links/{link_id}/stats/breakdown?by=browser", headers=headers_b).status_code == 404
    assert client.get(f"/api/links/{link_id}/qr", headers=headers_b).status_code == 404
