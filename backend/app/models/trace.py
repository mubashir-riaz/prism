"""Trace database model — records a single LLM inference call."""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.environment import Environment
    from app.models.project import Project

# JSONB with SQLite fallback for tests
JSONB_TYPE = JSONB().with_variant(JSON, "sqlite")


class Trace(TimestampedBase):
    """Trace entity representing a single LLM inference call ingested via the API.

    Traces are immutable after creation. They belong to a project and environment,
    and are optionally correlated to the API key used for ingestion. Deleting a
    project or environment cascades and removes all child traces. Rotating (deleting)
    an API key sets ``api_key_id`` to NULL so historical traces are preserved.
    """

    __tablename__ = "traces"
    __table_args__ = (
        # Composite indexes for the most common analytical query patterns.
        Index("ix_traces_project_id_created_at", "project_id", "created_at"),
        Index("ix_traces_feature_created_at", "feature", "created_at"),
        Index("ix_traces_model_created_at", "model", "created_at"),
        Index("ix_traces_organization_id_created_at", "organization_id", "created_at"),
    )

    # -------------------------------------------------------------------------
    # Foreign keys
    # -------------------------------------------------------------------------

    organization_id: Mapped[uuid.UUID] = mapped_column(
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
    environment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # SET NULL so traces survive API key rotation / deletion.
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Correlation / feature metadata
    # -------------------------------------------------------------------------

    # Client-supplied correlation ID for request tracing across services.
    request_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        index=True,
        nullable=True,
    )
    feature: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # LLM call data
    # -------------------------------------------------------------------------

    model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    completion: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Token accounting
    # -------------------------------------------------------------------------

    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Performance / cost
    # -------------------------------------------------------------------------

    latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    # Numeric(12, 6) → max value 999999.999999 USD; avoids float precision loss.
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Prompt versioning (Phase 10 will replace this with an FK)
    # -------------------------------------------------------------------------

    prompt_version: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Arbitrary caller-supplied metadata
    # -------------------------------------------------------------------------

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Relationships — lazy="raise" forces callers to explicitly eager-load
    # -------------------------------------------------------------------------

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="traces",
        lazy="raise",
    )
    environment: Mapped["Environment"] = relationship(
        "Environment",
        back_populates="traces",
        lazy="raise",
    )
    api_key: Mapped[Optional["APIKey"]] = relationship(
        "APIKey",
        back_populates="traces",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<Trace(id={self.id}, feature='{self.feature}', "
            f"model='{self.model}', project_id={self.project_id})>"
        )
