"""URL and alias validation service to prevent SSRF, open redirects, and route collisions.

Validates:
- HTTP and HTTPS protocol schemes
- Maximum length (2048 chars)
- Host presence and self-referencing check against BASE_URL
- Rejection of localhost, loopback, link-local, and private RFC-1918/RFC-4193 IP spaces
- Expiration timestamps in the future
- Custom alias syntax and reserved system keywords
"""

from datetime import datetime, timezone
import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import urlparse
from fastapi import HTTPException, status

from app.config import settings

# Set of system endpoints that short codes must never match
RESERVED_ALIASES = {
    "api",
    "auth",
    "docs",
    "redoc",
    "openapi.json",
    "health",
    "static",
    "admin",
    "login",
    "register",
}

ALIAS_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


def is_private_or_loopback_host(hostname: str) -> bool:
    """Checks whether the given hostname is localhost, private, or loopback IP."""
    lower_host = hostname.lower()
    if lower_host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    if lower_host.endswith((".localhost", ".local", ".internal")):
        return True

    # Check if host is direct IP address
    try:
        ip = ipaddress.ip_address(hostname)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except ValueError:
        pass

    # Resolve hostname via DNS to prevent DNS rebinding to private IPs
    try:
        resolved_ip_str = socket.gethostbyname(hostname)
        resolved_ip = ipaddress.ip_address(resolved_ip_str)
        return (
            resolved_ip.is_private
            or resolved_ip.is_loopback
            or resolved_ip.is_link_local
            or resolved_ip.is_reserved
            or resolved_ip.is_multicast
        )
    except Exception:
        pass

    return False


def validate_target_url(url: str) -> None:
    """Validates the destination URL syntax, host safety, and service boundaries."""
    if len(url) > 2048:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL length exceeds 2048 characters maximum limit.",
        )

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL scheme must be http or https.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must contain a valid host.",
        )

    # Self-host check: prevent shortening our own domain to avoid redirect loops
    service_host = urlparse(settings.BASE_URL).hostname
    if service_host and hostname.lower() == service_host.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot shorten URLs pointing to this service's own domain.",
        )

    # SSRF protection: reject private and loopback networks if enabled
    if settings.REJECT_PRIVATE_IPS and is_private_or_loopback_host(hostname):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shortening links to localhost, loopback, or private network addresses is forbidden.",
        )


def validate_expiration(expires_at: Optional[datetime]) -> None:
    """Ensures expiration timestamp is strictly in the future."""
    if expires_at is None:
        return

    now_utc = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        # Interpret naive datetime as UTC
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expiration timestamp must be in the future.",
        )


def validate_custom_alias(alias: str) -> None:
    """Validates custom alias character set and checks against reserved routing words."""
    if not ALIAS_PATTERN.match(alias):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alias must be 3 to 32 characters containing letters, digits, underscores, or hyphens.",
        )

    if alias.lower() in RESERVED_ALIASES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The alias '{alias}' is a reserved system keyword and cannot be used.",
        )
