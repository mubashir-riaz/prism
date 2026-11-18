"""Dataset database model — groups versioned eval datasets under a name."""

from typing import TYPE_CHECKING
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.dataset_version import DatasetVersion
    from app.models.organization import Organization
    from app.models.project import Project


class Dataset(TimestampedBase):
    """Named container for versioned eval datasets.

    A Dataset is scoped to a single project (and implicitly to an org).
    Each upload creates a new :class:`DatasetVersion`; the Dataset itself
    is just the stable identity that ties versions together.

    Constraints
    -----------
    ``(org_id, project_id, name)`` is unique — a project cannot have two
    datasets with the same name.  The org_id column is denormalized here
    so list queries can filter by org without joining through projects.
    """

    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "project_id",
            "name",
            name="uq_datasets_org_project_name",
        ),
    )

    # -------------------------------------------------------------------------
    # Foreign keys
    # -------------------------------------------------------------------------

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Attributes
    # -------------------------------------------------------------------------

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="datasets",
        lazy="raise",
    )
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="datasets",
        lazy="raise",
    )
    versions: Mapped[list["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="DatasetVersion.version_number",
    )

    def __repr__(self) -> str:
        return (
            f"<Dataset(id={self.id}, name='{self.name}', "
            f"project_id={self.project_id})>"
        )
