"""Pydantic schemas for DatasetVersion resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.dataset import DatasetRow


class DatasetVersionOut(BaseModel):
    """Read representation of a DatasetVersion, returned by upload and list endpoints.

    Fields
    ------
    duplicate
        Not stored in the database — set by the route layer when the upload
        produced no new version because an identical file (same content_hash)
        was already present.  Defaults to ``False`` for all non-duplicate
        responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    version_number: int
    content_hash: str
    row_count: int
    created_at: datetime

    # Synthetic field: populated by the route, never read from the ORM row.
    duplicate: bool = False


class DatasetVersionDetail(DatasetVersionOut):
    """Extended version read that includes a preview of the first rows.

    ``rows_preview`` is a subset of the full ``rows`` payload — the service
    layer decides how many rows to include (e.g. the first 10).  The full
    payload is available separately to avoid bloating list responses.
    """

    rows_preview: list[DatasetRow] = Field(default_factory=list)
