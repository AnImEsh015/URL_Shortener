"""Link CRUD router for managing shortened URLs.

Enforces:
- User authentication and strict ownership isolation (returning 404 rather than 403)
- Target URL and alias validation
- Unique code generation with collision retry loop (up to 5 attempts)
- Cache invalidation on PATCH and DELETE
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Link, User
from app.schemas import LinkCreateRequest, LinkListResponse, LinkResponse, LinkUpdateRequest
from app.services.cache import delete_cached_link
from app.services.codes import MAX_COLLISION_RETRIES, generate_short_code
from app.services.urls import (
    validate_custom_alias,
    validate_expiration,
    validate_target_url,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def build_link_response(link: Link) -> LinkResponse:
    """Helper to convert a Link ORM instance into LinkResponse with computed short_url."""
    short_url = f"{settings.BASE_URL.rstrip('/')}/{link.short_code}"
    return LinkResponse(
        id=link.id,
        short_code=link.short_code,
        short_url=short_url,
        original_url=link.original_url,
        expires_at=link.expires_at,
        max_clicks=link.max_clicks,
        click_count=link.click_count,
        created_at=link.created_at,
        is_active=link.is_active,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LinkResponse,
    summary="Create a new shortened link",
)
def create_link(
    payload: LinkCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a new shortened link with an optional custom alias and expiration."""
    validate_target_url(payload.url)
    validate_expiration(payload.expires_at)

    # 1. Custom alias handling
    if payload.custom_alias:
        validate_custom_alias(payload.custom_alias)

        # Check if alias already exists
        existing = db.execute(
            select(Link).where(Link.short_code == payload.custom_alias)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The alias '{payload.custom_alias}' is already in use.",
            )

        new_link = Link(
            user_id=current_user.id,
            short_code=payload.custom_alias,
            original_url=payload.url,
            expires_at=payload.expires_at,
            max_clicks=payload.max_clicks,
        )
        db.add(new_link)
        try:
            db.commit()
            db.refresh(new_link)
            return build_link_response(new_link)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The alias '{payload.custom_alias}' is already in use.",
            )

    # 2. Random code generation with collision retry loop
    for attempt in range(MAX_COLLISION_RETRIES):
        code = generate_short_code()
        new_link = Link(
            user_id=current_user.id,
            short_code=code,
            original_url=payload.url,
            expires_at=payload.expires_at,
            max_clicks=payload.max_clicks,
        )
        db.add(new_link)
        try:
            db.commit()
            db.refresh(new_link)
            return build_link_response(new_link)
        except IntegrityError:
            db.rollback()
            logger.warning(
                f"Collision detected on code '{code}' on attempt {attempt + 1}. Retrying..."
            )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique short code after maximum retry attempts. Please try again.",
    )


@router.get(
    "",
    response_model=LinkListResponse,
    summary="List current user's links with pagination",
)
def list_links(
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves a paginated list of short links belonging to the authenticated user."""
    offset = (page - 1) * page_size

    # Total count query
    total = db.execute(
        select(func.count()).select_from(Link).where(Link.user_id == current_user.id)
    ).scalar_one()

    # Paginated items query
    links = db.execute(
        select(Link)
        .where(Link.user_id == current_user.id)
        .order_by(Link.created_at.desc())
        .offset(offset)
        .limit(page_size)
    ).scalars().all()

    return LinkListResponse(
        items=[build_link_response(link) for link in links],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{id}",
    response_model=LinkResponse,
    summary="Get details of a specific link",
)
def get_link(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns metadata for a specific link owned by the authenticated user.

    Returns 404 (never 403) for links owned by another user to prevent enumeration.
    """
    link = db.execute(
        select(Link).where(Link.id == id, Link.user_id == current_user.id)
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found.",
        )

    return build_link_response(link)


@router.patch(
    "/{id}",
    response_model=LinkResponse,
    summary="Update link status, expiration, or click limit",
)
def update_link(
    id: int,
    payload: LinkUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modifies is_active, expires_at, or max_clicks on an existing link.

    Invalidates the Redis cache entry for the short code.
    Returns 404 if the link is not found or not owned by the current user.
    """
    link = db.execute(
        select(Link).where(Link.id == id, Link.user_id == current_user.id)
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found.",
        )

    if payload.expires_at is not None:
        validate_expiration(payload.expires_at)
        link.expires_at = payload.expires_at

    if payload.is_active is not None:
        link.is_active = payload.is_active

    if payload.max_clicks is not None:
        link.max_clicks = payload.max_clicks

    db.commit()
    db.refresh(link)

    # Invalidate cache so subsequent redirects read fresh metadata
    delete_cached_link(link.short_code)

    return build_link_response(link)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a link",
)
def delete_link(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently deletes a link and all its associated click analytics.

    Invalidates the Redis cache entry for the short code.
    Returns 404 if the link is not found or not owned by the current user.
    """
    link = db.execute(
        select(Link).where(Link.id == id, Link.user_id == current_user.id)
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found.",
        )

    short_code = link.short_code
    db.delete(link)
    db.commit()

    # Invalidate cache
    delete_cached_link(short_code)
    return None
