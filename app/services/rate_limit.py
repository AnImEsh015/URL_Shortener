"""Sliding window rate limiting using Redis sorted sets (ZSET).

Algorithm:
- Evaluates access frequency within a sliding temporal window [now - window_seconds, now].
- Performs ZREMRANGEBYSCORE, ZADD, ZCARD, and EXPIRE atomically in a Redis pipeline.
- If request count exceeds the limit, returns HTTP 429 Too Many Requests with a Retry-After header.
- Fails open on Redis connection/execution errors to avoid denying legitimate traffic during transient cache outages.
"""

import logging
import time
import uuid
from fastapi import HTTPException, status

from app.services.cache import get_redis_client

logger = logging.getLogger(__name__)


def check_rate_limit(identifier: str, limit: int, window_seconds: int) -> None:
    """Enforces sliding-window rate limit for a given key identifier.

    Raises HTTPException(429) with Retry-After header if limit exceeded.
    Fails open if Redis is unreachable.
    """
    key = f"ratelimit:{identifier}"
    now = time.time()
    clear_before = now - window_seconds
    member = f"{now}-{uuid.uuid4().hex[:8]}"

    try:
        r = get_redis_client()
        pipe = r.pipeline(transaction=True)
        # 1. Remove timestamps outside the sliding window
        pipe.zremrangebyscore(key, 0, clear_before)
        # 2. Add current request timestamp
        pipe.zadd(key, {member: now})
        # 3. Count requests currently in the window
        pipe.zcard(key)
        # 4. Set TTL on the sorted set to automatically clean up inactive keys
        pipe.expire(key, window_seconds)
        results = pipe.execute()

        request_count = results[2]

        if request_count > limit:
            # Query oldest element in current window to calculate accurate Retry-After seconds
            oldest_items = r.zrange(key, 0, 0, withscores=True)
            if oldest_items:
                oldest_timestamp = oldest_items[0][1]
                retry_after = max(1, int(window_seconds - (now - oldest_timestamp)))
            else:
                retry_after = window_seconds

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        # Re-raise 429
        raise
    except Exception as exc:
        # Fail open on Redis failure to preserve availability
        logger.warning(
            f"Redis rate limiter failed for identifier '{identifier}': {exc}. Failing open."
        )
