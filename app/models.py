"""SQLAlchemy 2.x typed declarative models for User, Link, and Click.

All timestamps are stored as timezone-aware UTC datetimes.
Models include indexes, foreign key relationships with cascading deletes,
and composite indexes for optimized analytics queries.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    """Helper to return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class User(Base):
    """User account model for authentication and ownership of links."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # email is stored in lowercase, indexed and unique for fast lookups during login/registration
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    links: Mapped[List["Link"]] = relationship(
        "Link",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Link(Base):
    """Shortened URL metadata model."""
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # short_code has a unique index to enforce collision avoidance at the database level
    short_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    max_clicks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="links")
    clicks: Mapped[List["Click"]] = relationship(
        "Click",
        back_populates="link",
        cascade="all, delete-orphan",
    )


class Click(Base):
    """Analytics click event recorded for each redirection."""
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    # Never store raw IP to protect user privacy; HMAC-SHA256 hex digest is 64 characters
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    browser: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    os: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Relationships
    link: Mapped["Link"] = relationship("Link", back_populates="clicks")

    # Composite index for filtering and aggregation by link and timestamp window
    __table_args__ = (
        Index("ix_clicks_link_id_clicked_at", "link_id", "clicked_at"),
    )
