"""FastAPI route dependencies for authentication and rate-limiting."""

from typing import Callable, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import decode_access_token
from app.services.rate_limit import check_rate_limit

# OAuth2 password bearer configuration points to the login route
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def extract_client_ip(request: Request) -> str:
    """Extracts client IP address respecting the TRUSTED_PROXY configuration."""
    if settings.TRUSTED_PROXY:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validates the JWT access token and returns the authenticated User instance.

    Raises HTTP 401 Unauthorized if the token is missing, expired, or the user
    no longer exists in the database.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_email: Optional[str] = payload.get("sub")
    if not user_email:
        raise credentials_exception

    user = db.execute(select(User).where(User.email == user_email)).scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user


def rate_limiter(
    key_prefix: str,
    get_limit: Callable[[], int],
    window_seconds: int,
):
    """Factory creating a rate limit dependency enforcing sliding-window access per IP."""
    def dependency(request: Request) -> None:
        ip = extract_client_ip(request)
        identifier = f"ip:{ip}:{key_prefix}"
        check_rate_limit(identifier, limit=get_limit(), window_seconds=window_seconds)

    return dependency
