"""Redirect router handling short code expansion, cache-aside lookups, and click event emission.

Design Principles:
- Cache-Aside: Reads from Redis `link:{code}` first; on miss queries PostgreSQL and seeds Redis.
- Negative Caching: Caches non-existent codes for 60 seconds to prevent DB hammering.
- Expiration & Inactive Checks: Returns HTTP 410 Gone for deactivated, expired, or limit-exceeded links.
- Max Clicks Enforcement: Monitored via Redis atomic counter `link:{id}:clicks`.
- Asynchronous Logging: Dispatches click analytics to Celery without blocking client redirection.
- Fail-Open Enqueue: If Celery/Redis message broker fails, error is logged and user is still redirected.
- HTTP 302 Found: Explicitly temporary redirect ensuring browsers do not cache the destination,
  preserving analytics tracking and access control.
"""

from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Link
from app.services.cache import (
    get_cached_link,
    get_redis_client,
    set_cached_link,
    set_negative_cached_link,
)
from app.worker import record_click

logger = logging.getLogger(__name__)

router = APIRouter()


def extract_client_ip(request: Request) -> str:
    """Extracts client IP address respecting the TRUSTED_PROXY configuration."""
    if settings.TRUSTED_PROXY:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # First IP in the comma-separated chain is the original client IP
            return forwarded_for.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


@router.get(
    "/{short_code}",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Redirect short code to target destination",
)
def redirect_to_url(
    short_code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Resolves short code, validates expiration and active status, and redirects with 302 Found."""
    now_utc = datetime.now(timezone.utc)
    cached_data = get_cached_link(short_code)

    link_id: Optional[int] = None
    target_url: Optional[str] = None
    expires_at_dt: Optional[datetime] = None
    max_clicks: Optional[int] = None
    is_active: bool = True

    if cached_data is not None:
        # Check for cached negative result (cache penetration prevention)
        if cached_data.get("status") == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Short link not found.",
            )

        link_id = cached_data["id"]
        target_url = cached_data["url"]
        is_active = cached_data.get("is_active", True)
        max_clicks = cached_data.get("max_clicks")
        exp_val = cached_data.get("expires_at")
        if exp_val:
            expires_at_dt = datetime.fromisoformat(exp_val)
            if expires_at_dt.tzinfo is None:
                expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
    else:
        # Cache miss: query PostgreSQL
        link = db.execute(
            select(Link).where(Link.short_code == short_code)
        ).scalar_one_or_none()

        if not link:
            # Negative cache for 60 seconds
            set_negative_cached_link(short_code, ttl=60)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Short link not found.",
            )

        link_id = link.id
        target_url = link.original_url
        is_active = link.is_active
        max_clicks = link.max_clicks
        expires_at_dt = link.expires_at

        # Calculate cache TTL: min(3600, seconds until expiration)
        ttl = 3600
        if expires_at_dt:
            if expires_at_dt.tzinfo is None:
                expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
            seconds_until_expiry = int((expires_at_dt - now_utc).total_seconds())
            if seconds_until_expiry <= 0:
                ttl = 1  # Expired or expiring immediately
            else:
                ttl = min(3600, seconds_until_expiry)

        cache_payload = {
            "id": link_id,
            "url": target_url,
            "expires_at": expires_at_dt.isoformat() if expires_at_dt else None,
            "max_clicks": max_clicks,
            "is_active": is_active,
        }
        set_cached_link(short_code, cache_payload, ttl=ttl)

        # Seed Redis click counter from database if not already present
        try:
            r = get_redis_client()
            r.set(f"link:{link_id}:clicks", link.click_count, nx=True)
        except Exception as e:
            logger.warning(f"Could not seed Redis click counter for link {link_id}: {e}")

    # 1. Active state verification
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This short link has been deactivated.",
        )

    # 2. Expiration verification
    if expires_at_dt and now_utc >= expires_at_dt:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This short link has expired.",
        )

    # 3. Max clicks verification
    if max_clicks is not None and link_id is not None:
        try:
            r = get_redis_client()
            current_clicks = r.incr(f"link:{link_id}:clicks")
            if current_clicks > max_clicks:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="This short link has reached its maximum click limit.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis click counter check failed for link {link_id}: {e}")

    # 4. Asynchronously enqueue analytics task via Celery
    client_ip = extract_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    referrer = request.headers.get("Referer", "")

    try:
        record_click.delay(
            link_id=link_id,
            client_ip=client_ip,
            user_agent_str=user_agent,
            referrer=referrer,
            clicked_at_iso=now_utc.isoformat(),
        )
    except Exception as exc:
        logger.warning(
            f"Failed to enqueue record_click background task for link {link_id}: {exc}"
        )

    # 5. Return 302 temporary redirect
    return RedirectResponse(
        url=target_url,
        status_code=status.HTTP_302_FOUND,
    )
