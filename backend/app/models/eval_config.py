"""EvalConfig database model — stores a named set of evaluator configurations."""

from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.project import Project

# JSONB with SQLite fallback for the test suite
JSONB_TYPE = JSONB().with_variant(JSON, "sqlite")


class EvalConfig(TimestampedBase):
    """A named, reusable evaluator configuration scoped to a project.

    Stores a list of evaluator descriptors — each with a name, weight, and
    optional params — as a JSONB column.  The evaluation runner in Phase 6
    reads this config and passes each entry to the registry's
    ``build_evaluator`` factory.

    Schema of the ``evaluators`` JSON array
    ----------------------------------------
    Each element is a dict with:

    ``name`` (str, required)
        Registered evaluator name, e.g. ``"exact_match"``.
    ``weight`` (float, required)
        Relative weight used by ``weighted_average``.
    ``params`` (dict, optional)
        Constructor kwargs forwarded to the evaluator class.

    Example::

        [
            {"name": "exact_match", "weight": 1.0},
            {"name": "contains",    "weight": 0.5},
            {"name": "length_bounds", "weight": 0.5, "params": {"min_len": 1, "max_len": 500}},
        ]

    Constraints
    -----------
    ``(org_id, project_id, name)`` is unique — a project cannot have two
    configs with the same name.  ``org_id`` is denormalised here so list
    queries can filter by org without joining through projects.
    """

    __tablename__ = "eval_configs"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "project_id",
            "name",
            name="uq_eval_configs_org_project_name",
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
    evaluators: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        server_default=text("'[]'"),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="eval_configs",
        lazy="raise",
    )
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="eval_configs",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<EvalConfig(id={self.id}, name={self.name!r}, "
            f"project_id={self.project_id})>"
        )
