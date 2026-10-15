"""Authentication router for user registration and JWT login."""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import rate_limiter
from app.models import User
from app.schemas import TokenResponse, UserRegisterRequest, UserResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter()

limit_login = rate_limiter("login", lambda: settings.RATE_LIMIT_LOGIN_PER_MIN, 60)
limit_register = rate_limiter("register", lambda: settings.RATE_LIMIT_REGISTER_PER_HOUR, 3600)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    dependencies=[Depends(limit_register)],
    summary="Register a new user account",
)
def register(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
):
    """Creates a new user account with lowercase email and securely hashed password.

    Returns HTTP 409 Conflict if an account with this email already exists.
    """
    normalized_email = payload.email.lower().strip()

    # Check if user already exists
    existing = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    # Hash password with bcrypt directly
    hashed = hash_password(payload.password)
    new_user = User(
        email=normalized_email,
        password_hash=hashed,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit_login)],
    summary="Authenticate and receive JWT access token",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticates using email (in form username field) and password.

    Compatible with standard OAuth2 password flow for Swagger UI Authorize button.
    Returns HTTP 401 Unauthorized on invalid credentials.
    """
    normalized_email = form_data.username.lower().strip()

    user = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Issue JWT access token
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": user.email, "uid": user.id},
        expires_delta=expires_delta,
    )

    return TokenResponse(access_token=token, token_type="bearer")
