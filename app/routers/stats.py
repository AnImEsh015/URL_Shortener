"""Analytics statistics router providing aggregations, timeseries, and categorical breakdowns.

Features:
- Authentication and strict ownership isolation (404 on unowned links)
- Cached analytics responses in Redis for 60 seconds
- Safe parameterized aggregation queries without SQL string interpolation
- Timeseries grouping via PostgreSQL date_trunc
"""

import io
import json
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Click, Link, User
from app.schemas import BreakdownPoint, StatsSummaryResponse, TimeseriesPoint
from app.services.cache import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


class TimeseriesInterval(StrEnum):
    """Allowed intervals for timeseries aggregation."""
    day = "day"
    hour = "hour"


class BreakdownDimension(StrEnum):
    """Allowed categorical breakdown dimensions."""
    country = "country"
    device = "device"
    browser = "browser"
    os = "os"
    referrer = "referrer"


# Safe mapping from validated enum to SQLAlchemy model columns
DIMENSION_COLUMN_MAP = {
    BreakdownDimension.country: Click.country,
    BreakdownDimension.device: Click.device_type,
    BreakdownDimension.browser: Click.browser,
    BreakdownDimension.os: Click.os,
    BreakdownDimension.referrer: Click.referrer,
}


def get_cached_json(cache_key: str) -> Any | None:
    """Retrieves cached JSON payload from Redis."""
    if not settings.CACHE_ENABLED:
        return None
    try:
        r = get_redis_client()
        val = r.get(cache_key)
        if val:
            return json.loads(val)
    except Exception as e:
        logger.warning(f"Stats cache read error for key {cache_key}: {e}")
    return None


def set_cached_json(cache_key: str, data: Any, ttl: int = 60) -> None:
    """Stores JSON payload into Redis with a TTL in seconds."""
    if not settings.CACHE_ENABLED:
        return
    try:
        r = get_redis_client()
        r.set(cache_key, json.dumps(data, default=str), ex=ttl)
    except Exception as e:
        logger.warning(f"Stats cache write error for key {cache_key}: {e}")


def verify_link_ownership(link_id: int, current_user: User, db: Session) -> Link:
    """Verifies that the link exists and is owned by the authenticated user.

    Returns 404 (never 403) to prevent unauthorized enumeration.
    """
    link = db.execute(
        select(Link).where(Link.id == link_id, Link.user_id == current_user.id)
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found.",
        )
    return link


@router.get(
    "/{id}/stats",
    response_model=StatsSummaryResponse,
    summary="Get overall link analytics summary",
)
def get_link_stats(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns total clicks, unique visitors (COUNT DISTINCT ip_hash), and click timestamp bounds."""
    verify_link_ownership(id, current_user, db)

    cache_key = f"stats:{id}:summary"
    cached = get_cached_json(cache_key)
    if cached:
        return StatsSummaryResponse(**cached)

    result = db.execute(
        select(
            func.count(Click.id).label("total_clicks"),
            func.count(func.distinct(Click.ip_hash)).label("unique_visitors"),
            func.min(Click.clicked_at).label("first_click_at"),
            func.max(Click.clicked_at).label("last_click_at"),
        ).where(Click.link_id == id)
    ).one()

    stats_data = {
        "total_clicks": result.total_clicks or 0,
        "unique_visitors": result.unique_visitors or 0,
        "first_click_at": result.first_click_at.isoformat() if result.first_click_at else None,
        "last_click_at": result.last_click_at.isoformat() if result.last_click_at else None,
    }
    set_cached_json(cache_key, stats_data, ttl=60)

    return StatsSummaryResponse(**stats_data)


@router.get(
    "/{id}/stats/timeseries",
    response_model=list[TimeseriesPoint],
    summary="Get click timeseries bucketed by day or hour",
)
def get_link_timeseries(
    id: int,
    interval: TimeseriesInterval = Query(TimeseriesInterval.day, description="Bucket interval (day or hour)"),
    days: int = Query(30, ge=1, le=365, description="Lookback period in days (1 to 365)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregates clicks over time using SQL date_trunc, grouped and ordered chronologically."""
    verify_link_ownership(id, current_user, db)

    cache_key = f"stats:{id}:timeseries:{interval.value}:{days}"
    cached = get_cached_json(cache_key)
    if cached:
        return [TimeseriesPoint(**point) for point in cached]

    cutoff_dt = datetime.now(UTC) - timedelta(days=days)

    bucket_col = func.date_trunc(interval.value, Click.clicked_at).label("bucket")
    rows = db.execute(
        select(
            bucket_col,
            func.count(Click.id).label("clicks"),
        )
        .where(Click.link_id == id, Click.clicked_at >= cutoff_dt)
        .group_by(bucket_col)
        .order_by(bucket_col.asc())
    ).all()

    points = [
        {
            "bucket": row.bucket.isoformat() if hasattr(row.bucket, "isoformat") else str(row.bucket),
            "clicks": row.clicks,
        }
        for row in rows
    ]
    set_cached_json(cache_key, points, ttl=60)

    return [TimeseriesPoint(**p) for p in points]


@router.get(
    "/{id}/stats/breakdown",
    response_model=list[BreakdownPoint],
    summary="Get categorical click breakdown",
)
def get_link_breakdown(
    id: int,
    by: BreakdownDimension = Query(..., description="Categorical dimension to segment by"),
    limit: int = Query(10, ge=1, le=100, description="Top N categories to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Segments click counts across validated categorical dimensions (country, device, browser, etc.).

    Column selection uses a type-safe map and is never interpolated into raw SQL.
    """
    verify_link_ownership(id, current_user, db)

    cache_key = f"stats:{id}:breakdown:{by.value}:{limit}"
    cached = get_cached_json(cache_key)
    if cached:
        return [BreakdownPoint(**point) for point in cached]

    col = DIMENSION_COLUMN_MAP[by]
    # Coalesce null values to 'Unknown' for clean client display
    key_expr = func.coalesce(col, "Unknown").label("key")

    rows = db.execute(
        select(
            key_expr,
            func.count(Click.id).label("clicks"),
        )
        .where(Click.link_id == id)
        .group_by(key_expr)
        .order_by(func.count(Click.id).desc())
        .limit(limit)
    ).all()

    points = [{"key": row.key, "clicks": row.clicks} for row in rows]
    set_cached_json(cache_key, points, ttl=60)

    return [BreakdownPoint(**p) for p in points]


@router.get(
    "/{id}/qr",
    summary="Get QR code image (PNG) for shortened link",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image binary stream of the QR code.",
        }
    },
)
def get_link_qr_code(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generates a high-contrast PNG QR code for the shortened link.

    Cached in Redis for 60 seconds.
    """
    link = verify_link_ownership(id, current_user, db)

    cache_key = f"stats:{id}:qr"
    if settings.CACHE_ENABLED:
        try:
            r = get_redis_client()
            cached_bytes = r.get(cache_key)
            if cached_bytes:
                # Redis returns string or bytes; if string, encode
                raw_bytes = cached_bytes if isinstance(cached_bytes, bytes) else cached_bytes.encode("latin1")
                return Response(content=raw_bytes, media_type="image/png")
        except Exception as e:
            logger.warning(f"Error reading QR cache: {e}")

    short_url = f"{settings.BASE_URL.rstrip('/')}/{link.short_code}"

    # Generate QR Code using Pillow PIL
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(short_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    if settings.CACHE_ENABLED:
        try:
            r = get_redis_client()
            # Store binary string in Redis
            r.set(cache_key, png_bytes.decode("latin1"), ex=60)
        except Exception as e:
            logger.warning(f"Error saving QR cache: {e}")

    return Response(content=png_bytes, media_type="image/png")

