"""Auth Pydantic schemas — registration, login, tokens, and /me."""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings
from app.models.enums import UserRole
from app.schemas.user import UserRead


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    email: EmailStr = Field(..., description="User email address.")
    password: str = Field(
        ...,
        min_length=8,  # hard lower-bound; the validator also checks settings value
        description="Account password.",
    )
    full_name: Optional[str] = Field(None, max_length=255, description="Display name.")
    organization_slug: str = Field(
        ...,
        min_length=2,
        max_length=63,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe slug for the new organisation (e.g. 'acme-corp').",
    )
    role: UserRole = Field(
        default=UserRole.MEMBER,
        description="Role the user will hold in the new organisation.",
    )

    @field_validator("password")
    @classmethod
    def password_meets_minimum_length(cls, v: str) -> str:
        min_len = settings.PASSWORD_MIN_LENGTH
        if len(v) < min_len:
            raise ValueError(
                f"Password must be at least {min_len} characters long."
            )
        return v


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    email: EmailStr = Field(..., description="Registered email address.")
    password: str = Field(..., description="Account password.")


# ---------------------------------------------------------------------------
# Token response
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """Returned by login and refresh endpoints."""

    access_token: str = Field(..., description="Signed JWT access token.")
    token_type: str = Field(default="bearer", description="OAuth2 token type.")
    expires_in: int = Field(
        ...,
        description="Seconds until the token expires.",
    )


# ---------------------------------------------------------------------------
# /me response
# ---------------------------------------------------------------------------

# UserRead already carries: id, email, full_name, role, organization_id,
# is_active, last_login_at, created_at, updated_at — exactly what /me needs.
# We alias it so the auth layer has a stable, self-documenting name to import.
MeResponse = UserRead

__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "MeResponse",
]
