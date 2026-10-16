"""APIKey Pydantic schemas."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class APIKeyBase(BaseModel):
    """Base schema for API key attributes."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name for the API key")


class APIKeyCreate(APIKeyBase):
    """Schema for creating a new API key."""

    project_id: uuid.UUID = Field(..., description="Project ID this API key belongs to")
    environment_id: uuid.UUID = Field(..., description="Environment ID this API key belongs to")


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated name")
    is_active: Optional[bool] = Field(None, description="Updated active status")


class APIKeyRead(APIKeyBase):
    """Schema for reading API key metadata without the secret."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    environment_id: uuid.UUID
    key_prefix: str = Field(..., description="Public prefix identifying the key")
    is_active: bool
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class APIKeyCreateResponse(APIKeyRead):
    """Schema returned once upon creation containing the unrecoverable plaintext key."""

    plaintext_key: str = Field(
        ...,
        description="Plaintext API key. This is returned only once upon creation and cannot be retrieved later.",
    )
