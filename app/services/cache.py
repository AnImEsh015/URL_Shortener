"""Redis cache service for link metadata, rate limiting, and analytics.

Uses the synchronous redis-py client with connection pooling and timeout handling.
Provides caching helpers with cache-aside semantics and negative caching.
"""

import json
import logging
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)

# Reusable Redis client instance
_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Returns a singleton Redis client instance configured with timeouts."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_client


def set_redis_client(client: redis.Redis) -> None:
    """Allows setting custom Redis client, useful for injecting fakeredis in tests."""
    global _redis_client
    _redis_client = client


def get_cached_link(short_code: str) -> dict[str, Any] | None:
    """Retrieves link cache entry by short code. Returns None on cache miss or Redis failure."""
    if not settings.CACHE_ENABLED:
        return None
    try:
        r = get_redis_client()
        val = r.get(f"link:{short_code}")
        if val is None:
            return None
        return json.loads(val)
    except Exception as e:
        logger.warning(f"Redis get_cached_link error for code {short_code}: {e}")
        return None


def set_cached_link(short_code: str, data: dict[str, Any], ttl: int) -> None:
    """Caches link metadata with a defined TTL in seconds."""
    if not settings.CACHE_ENABLED or ttl <= 0:
        return
    try:
        r = get_redis_client()
        r.set(f"link:{short_code}", json.dumps(data), ex=ttl)
    except Exception as e:
        logger.warning(f"Redis set_cached_link error for code {short_code}: {e}")


def set_negative_cached_link(short_code: str, ttl: int = 60) -> None:
    """Caches a 404 miss for short duration to prevent cache penetration."""
    if not settings.CACHE_ENABLED:
        return
    try:
        r = get_redis_client()
        r.set(f"link:{short_code}", json.dumps({"status": "not_found"}), ex=ttl)
    except Exception as e:
        logger.warning(f"Redis set_negative_cached_link error for code {short_code}: {e}")


def delete_cached_link(short_code: str) -> None:
    """Invalidates the cached link entry on update or deletion."""
    try:
        r = get_redis_client()
        r.delete(f"link:{short_code}")
    except Exception as e:
        logger.warning(f"Redis delete_cached_link error for code {short_code}: {e}")
