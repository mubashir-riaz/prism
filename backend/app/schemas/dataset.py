"""Pydantic schemas for Dataset resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetRow(BaseModel):
    """A single row in an eval dataset.

    Fields
    ------
    input
        The prompt or question sent to the LLM during evaluation.
    expected
        The reference / gold-standard answer the LLM should produce.
    metadata
        Optional arbitrary caller-supplied key/value data (e.g. tags,
        difficulty rating, source document ID).  ``None`` when absent.
    """

    input: str
    expected: str
    metadata: dict | None = None


class DatasetIn(BaseModel):
    """Payload for creating a new Dataset (name + project scope).

    Validation
    ----------
    ``name`` is 1–200 characters — the same upper bound as the ``datasets``
    table column.  Empty names are explicitly rejected (``min_length=1``).
    ``project_id`` is required; the service layer verifies it belongs to the
    caller's org before inserting.
    """

    name: str = Field(..., min_length=1, max_length=200)
    project_id: UUID


class DatasetOut(BaseModel):
    """Full read representation of a Dataset."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    project_id: UUID
    name: str
    created_at: datetime
