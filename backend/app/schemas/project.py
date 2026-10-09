"""Project Pydantic schemas."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.environment import EnvironmentRead


class ProjectBase(BaseModel):
    """Base schema for project attributes."""

    name: str = Field(..., min_length=1, max_length=255, description="Project display name")
    slug: str = Field(..., min_length=1, max_length=255, description="Unique project slug within organization")
    description: Optional[str] = Field(None, description="Optional project description")


class ProjectCreate(ProjectBase):
    """Schema for creating a new project within an organization."""

    organization_id: uuid.UUID = Field(..., description="Organization ID the project belongs to")


class ProjectUpdate(BaseModel):
    """Schema for updating project details with optional fields."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated project name")
    slug: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated project slug")
    description: Optional[str] = Field(None, description="Updated project description")
    is_archived: Optional[bool] = Field(None, description="Archived status of the project")


class ProjectRead(ProjectBase):
    """Schema for reading project details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    environments: list[EnvironmentRead] = []
