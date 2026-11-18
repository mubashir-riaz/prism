"""DatasetVersion database model — an immutable snapshot of uploaded eval rows."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.dataset import Dataset

# JSONB with SQLite fallback for the test suite
JSONB_TYPE = JSONB().with_variant(JSON, "sqlite")


class DatasetVersion(Base):
    """Immutable snapshot of a single dataset upload.

    Every upload of a JSONL file produces one DatasetVersion.  The same file
    uploaded twice yields the same ``content_hash``, which triggers the
    idempotency constraint ``uq_dataset_versions_dataset_content_hash`` and
    prevents a redundant version from being stored.

    Columns
    -------
    version_number
        Monotonically incrementing integer within a dataset (1, 2, 3 …).
        Assigned by the service layer, not a DB sequence, so the service can
        read the current max and +1 inside a single transaction.
    content_hash
        SHA-256 hex digest (64 chars) of the canonicalised JSONL bytes.
        Used for idempotency: same file → same hash → no duplicate version.
    row_count
        Denormalised count of rows in ``rows``.  Stored explicitly so callers
        can read it without deserialising the full JSONB payload.
    rows
        JSONB array of parsed dataset rows.  Each element is a dict with at
        least ``input`` and ``expected`` keys; an optional ``metadata`` key
        carries arbitrary caller-supplied fields.

    Constraints
    -----------
    ``(dataset_id, version_number)`` — no two versions share the same number.
    ``(dataset_id, content_hash)``   — no duplicate file content per dataset.
    """

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "version_number",
            name="uq_dataset_versions_dataset_version_number",
        ),
        UniqueConstraint(
            "dataset_id",
            "content_hash",
            name="uq_dataset_versions_dataset_content_hash",
        ),
    )

    # -------------------------------------------------------------------------
    # Primary key
    # -------------------------------------------------------------------------

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # -------------------------------------------------------------------------
    # Foreign key
    # -------------------------------------------------------------------------

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Versioning
    # -------------------------------------------------------------------------

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        # SHA-256 produces a 64-character hex string.
        String(64),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Payload
    # -------------------------------------------------------------------------

    row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    rows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Timestamps — created_at only; versions are immutable after insertion.
    # -------------------------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------

    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="versions",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetVersion(id={self.id}, dataset_id={self.dataset_id}, "
            f"version={self.version_number}, rows={self.row_count})>"
        )
