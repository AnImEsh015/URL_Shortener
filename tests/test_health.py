"""Tests for /health endpoint."""

from unittest.mock import MagicMock, patch


def test_health_check_healthy(client):
    """Verifies that /health returns 200 OK when both PostgreSQL and Redis are responsive."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["redis"] == "ok"


def test_health_check_database_down(client):
    """Verifies that /health returns 503 Service Unavailable when the database is unreachable."""
    with patch("app.main.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database connection refused")
        mock_session.return_value = mock_db

        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "down"


def test_health_check_redis_down(client):
    """Verifies that /health returns 503 Service Unavailable when Redis is unreachable."""
    with patch("app.main.get_redis_client") as mock_redis_func:
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis connection refused")
        mock_redis_func.return_value = mock_redis

        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["redis"] == "down"
