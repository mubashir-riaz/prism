"""AuditLog Pydantic schemas."""

from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from app.models.enums import AuditAction


class AuditLogBase(BaseModel):
    """Base schema for audit log attributes."""

    action: AuditAction = Field(..., description="Action recorded in the audit log")
    resource_type: str = Field(..., min_length=1, max_length=255, description="Type of target resource")
    resource_id: Optional[uuid.UUID] = Field(None, description="ID of target resource")
    metadata_json: dict[str, Any] = Field(default_factory=dict, description="Arbitrary event metadata payload")
    ip_address: Optional[str] = Field(None, max_length=255, description="Client IP address")
    user_agent: Optional[str] = Field(None, max_length=1024, description="Client User-Agent header")


class AuditLogCreate(AuditLogBase):
    """Schema for creating a new immutable audit log entry."""

    organization_id: uuid.UUID = Field(..., description="Organization ID where the action occurred")
    actor_user_id: Optional[uuid.UUID] = Field(None, description="User ID performing the action, or None for system actions")
