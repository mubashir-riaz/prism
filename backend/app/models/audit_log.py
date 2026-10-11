"""AuditLog database model."""

from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import TimestampedBase
from app.models.enums import AuditAction

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User

JSONB_TYPE = JSONB().with_variant(JSON, "sqlite")


class AuditLog(TimestampedBase):
    """Immutable, append-only audit log recording security and domain events."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_audit_logs_resource_type_resource_id", "resource_type", "resource_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, native_enum=False, length=50),
        index=True,
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        index=True,
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="audit_logs",
    )
    actor_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="audit_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"resource_type='{self.resource_type}', resource_id={self.resource_id})>"
        )
