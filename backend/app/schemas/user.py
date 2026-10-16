"""User Pydantic schemas."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class UserBase(BaseModel):
    """Base schema for user attributes."""

    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    full_name: Optional[str] = Field(None, max_length=255, description="User display name")
    role: UserRole = Field(default=UserRole.MEMBER, description="User role in the organization")


class UserCreate(UserBase):
    """Schema for creating a new user within an organization."""

    organization_id: uuid.UUID = Field(..., description="Organization ID the user belongs to")


class UserUpdate(BaseModel):
    """Schema for updating user details with optional fields."""

    full_name: Optional[str] = Field(None, max_length=255, description="Updated full name")
    role: Optional[UserRole] = Field(None, description="Updated user role")
    is_active: Optional[bool] = Field(None, description="Updated active status")


class UserRead(UserBase):
    """Schema for reading user details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
