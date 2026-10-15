"""Analytics service for IP hashing, User-Agent parsing, GeoIP resolution, and DB persistence.

Security & Privacy:
- Never stores raw IP addresses. Hashes client IP with HMAC-SHA256 using IP_HASH_SALT.
- Unique visitors are counted via `COUNT(DISTINCT ip_hash)`.
- GeoIP lookup is optional; fails gracefully if MaxMind DB is missing.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import logging
import os
from typing import Optional, Tuple
from sqlalchemy import update
from user_agents import parse as parse_user_agent

from app.config import settings
from app.db import SessionLocal
from app.models import Click, Link

logger = logging.getLogger(__name__)

# GeoIP Reader instance cache
_geoip_reader = None
_geoip_warned = False


def hash_client_ip(ip: str) -> str:
    """Computes HMAC-SHA256 hash of client IP using IP_HASH_SALT secret.

    Returns a 64-character hexadecimal digest. Raw IP is discarded immediately.
    """
    key = settings.IP_HASH_SALT.encode("utf-8")
    msg = ip.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def parse_user_agent_string(ua_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extracts browser, OS, and device classification from User-Agent string."""
    if not ua_str:
        return None, None, None

    try:
        ua = parse_user_agent(ua_str)
        browser = ua.browser.family if ua.browser.family else None
        os_name = ua.os.family if ua.os.family else None

        if ua.is_mobile:
            device = "mobile"
        elif ua.is_tablet:
            device = "tablet"
        elif ua.is_pc:
            device = "desktop"
        elif ua.is_bot:
            device = "bot"
        else:
            device = "other"

        return browser, os_name, device
    except Exception as e:
        logger.warning(f"Failed to parse User-Agent header '{ua_str}': {e}")
        return None, None, None


def resolve_geoip(ip: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolves country name and city name from MaxMind GeoLite2 database if available."""
    global _geoip_reader, _geoip_warned

    db_path = settings.GEOIP_DB_PATH
    if not db_path or not os.path.exists(db_path):
        if not _geoip_warned:
            logger.warning(
                "GeoIP database path is unset or file not found. Country and city will be stored as NULL."
            )
            _geoip_warned = True
        return None, None

    try:
        import geoip2.database
        if _geoip_reader is None:
            _geoip_reader = geoip2.database.Reader(db_path)

        resp = _geoip_reader.city(ip)
        country = resp.country.name
        city = resp.city.name
        return country, city
    except Exception:
        return None, None


def process_click_event(
    link_id: int,
    client_ip: str,
    user_agent_str: str,
    referrer: str,
    clicked_at_iso: str,
) -> None:
    """Processes click event and stores it into PostgreSQL with atomic count increment."""
    db = SessionLocal()
    try:
        # 1. Privacy-safe IP hashing
        ip_hash = hash_client_ip(client_ip)

        # 2. User-Agent parsing
        browser, os_name, device_type = parse_user_agent_string(user_agent_str)

        # 3. GeoIP lookup
        country, city = resolve_geoip(client_ip)

        # 4. Parse timestamp
        clicked_at = datetime.fromisoformat(clicked_at_iso)
        if clicked_at.tzinfo is None:
            clicked_at = clicked_at.replace(tzinfo=timezone.utc)

        # 5. Insert Click record
        click = Click(
            link_id=link_id,
            clicked_at=clicked_at,
            ip_hash=ip_hash,
            country=country,
            city=city,
            device_type=device_type,
            browser=browser,
            os=os_name,
            referrer=referrer if referrer else None,
        )
        db.add(click)

        # 6. Atomic increment on links.click_count
        db.execute(
            update(Link)
            .where(Link.id == link_id)
            .values(click_count=Link.click_count + 1)
        )

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to record click for link {link_id}: {exc}")
        raise exc
    finally:
        db.close()
