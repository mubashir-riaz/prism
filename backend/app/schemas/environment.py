"""Environment Pydantic schemas."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EnvironmentName


class EnvironmentBase(BaseModel):
    """Base schema for environment attributes."""

    name: EnvironmentName = Field(..., description="Environment tier name (dev, staging, prod)")
    is_default: bool = Field(default=False, description="Whether this is the default project environment")


class EnvironmentCreate(EnvironmentBase):
    """Schema for creating a new environment within a project."""

    project_id: uuid.UUID = Field(..., description="Project ID the environment belongs to")


class EnvironmentUpdate(BaseModel):
    """Schema for updating an environment."""

    name: Optional[EnvironmentName] = Field(None, description="Updated environment name")
    is_default: Optional[bool] = Field(None, description="Updated default status")


class EnvironmentRead(EnvironmentBase):
    """Schema for reading environment details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
