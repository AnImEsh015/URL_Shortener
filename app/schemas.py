"""Pydantic v2 data validation schemas for requests and responses."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


# ---------------------------------------------------------
# Authentication Schemas
# ---------------------------------------------------------

class UserRegisterRequest(BaseModel):
    """Payload for user registration."""
    email: str
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not EMAIL_REGEX.match(cleaned):
            raise ValueError("Invalid email address format.")
        return cleaned


class UserResponse(BaseModel):
    """Public user profile response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


class TokenResponse(BaseModel):
    """OAuth2 compatible JWT token response."""
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------
# Link Management Schemas
# ---------------------------------------------------------

class LinkCreateRequest(BaseModel):
    """Payload for creating a new short link."""
    url: str = Field(..., max_length=2048, description="Target destination URL")
    custom_alias: str | None = Field(
        None,
        min_length=3,
        max_length=32,
        description="Optional custom short code alias",
    )
    expires_at: datetime | None = Field(
        None,
        description="Optional expiration datetime in UTC (must be in the future)",
    )
    max_clicks: int | None = Field(
        None,
        gt=0,
        description="Optional maximum allowed clicks before link deactivates",
    )


class LinkUpdateRequest(BaseModel):
    """Payload for updating an existing link's settings."""
    is_active: bool | None = Field(None, description="Toggle link active state")
    expires_at: datetime | None = Field(None, description="Update link expiration timestamp")
    max_clicks: int | None = Field(None, gt=0, description="Update click limit (null to remove limit)")


class LinkResponse(BaseModel):
    """Representation of a shortened link returned to users."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    short_code: str
    short_url: str
    original_url: str
    expires_at: datetime | None
    max_clicks: int | None
    click_count: int
    created_at: datetime
    is_active: bool


class LinkListResponse(BaseModel):
    """Paginated collection of links."""
    items: list[LinkResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------
# Analytics Schemas
# ---------------------------------------------------------

class StatsSummaryResponse(BaseModel):
    """High-level analytics overview for a specific link."""
    total_clicks: int
    unique_visitors: int
    first_click_at: datetime | None
    last_click_at: datetime | None


class TimeseriesPoint(BaseModel):
    """Data point in a timeseries aggregation."""
    bucket: datetime
    clicks: int


class BreakdownPoint(BaseModel):
    """Data point in a categorical breakdown aggregation."""
    key: str
    clicks: int
