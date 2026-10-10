"""Environment database model."""

from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import TimestampedBase
from app.models.enums import EnvironmentName

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.project import Project


class Environment(TimestampedBase):
    """Environment entity belonging to a project (e.g. dev, staging, prod)."""

    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_environments_project_id_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False, length=50),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="environments",
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="environment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Environment(id={self.id}, name='{self.name}', project_id={self.project_id}, is_default={self.is_default})>"
