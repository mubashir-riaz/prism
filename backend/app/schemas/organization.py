"""Organization Pydantic schemas."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class OrganizationBase(BaseModel):
    """Base schema for organization attributes."""

    name: str = Field(..., min_length=1, max_length=255, description="Organization display name")
    slug: str = Field(..., min_length=1, max_length=255, description="Unique organization slug identifier")


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating an existing organization with optional fields."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated organization name")
    slug: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated organization slug")
    is_active: Optional[bool] = Field(None, description="Active status of the organization")


class OrganizationRead(OrganizationBase):
    """Schema for reading organization details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
