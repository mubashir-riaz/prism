"""Dataset service — upload, versioning, and deduplication logic."""

import uuid
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    DatasetNotFoundError,
    EmptyDatasetError,
    FileTooLargeError,
    RowValidationError,
    TooManyRowsError,
)
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.repositories.dataset_repository import DatasetRepository
from app.schemas.dataset import DatasetRow
from app.schemas.dataset_version import DatasetVersionDetail
from app.utils.hashing import sha256_hex
from app.utils.jsonl import InvalidJSONLError, parse_jsonl  # noqa: F401 — re-exported for callers

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

MAX_ROWS: int = 10_000
MAX_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_repo = DatasetRepository()


async def create_dataset(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    name: str,
) -> Dataset:
    """Create and return a new named Dataset.

    The unique constraint ``(org_id, project_id, name)`` on the table means
    a duplicate name within the same project raises
    ``sqlalchemy.exc.IntegrityError`` — intentionally not caught here; the
    route layer translates it into an HTTP 409.
    """
    dataset = await _repo.create_dataset(
        db,
        org_id=org_id,
        project_id=project_id,
        name=name,
    )
    await db.commit()
    return dataset


async def list_datasets(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> list[Dataset]:
    """Return all datasets visible to an organisation, optionally filtered by project."""
    return await _repo.list_datasets(db, org_id=org_id, project_id=project_id)


async def list_versions(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[DatasetVersion]:
    """Return all versions for a dataset, verifying org ownership first.

    Raises :class:`~app.exceptions.DatasetNotFoundError` if the dataset does
    not exist or belongs to a different org.
    """
    dataset = await _repo.get_dataset(db, dataset_id=dataset_id, org_id=org_id)
    if dataset is None:
        raise DatasetNotFoundError(
            f"Dataset '{dataset_id}' not found.",
            details={"dataset_id": str(dataset_id)},
        )
    return await _repo.list_versions(db, dataset_id=dataset_id)


async def get_version_detail(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    version_number: int,
    org_id: uuid.UUID,
    preview_limit: int = 10,
) -> DatasetVersionDetail | None:
    """Return detailed version info including a row preview.

    Returns ``None`` if the version does not exist (or the dataset belongs to
    another org).  The ``rows_preview`` field contains the first
    *preview_limit* rows; callers control how many rows to surface.
    """
    # Verify org ownership
    dataset = await _repo.get_dataset(db, dataset_id=dataset_id, org_id=org_id)
    if dataset is None:
        return None

    version = await _repo.get_version_by_number(
        db, dataset_id=dataset_id, version_number=version_number
    )
    if version is None:
        return None

    preview_rows = [
        DatasetRow(**row) for row in version.rows[:preview_limit]
    ]
    return DatasetVersionDetail(
        id=version.id,
        dataset_id=version.dataset_id,
        version_number=version.version_number,
        content_hash=version.content_hash,
        row_count=version.row_count,
        created_at=version.created_at,
        rows_preview=preview_rows,
    )


async def upload_version(
    db: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    org_id: uuid.UUID,
    file_bytes: bytes,
) -> tuple[DatasetVersion, bool]:
    """Parse a JSONL file and persist it as a new DatasetVersion.

    Returns
    -------
    (version, was_duplicate)
        ``was_duplicate=True`` when an identical file (same content_hash) was
        already stored; no new DB row is written in that case.

    Raises
    ------
    DatasetNotFoundError
        Dataset does not exist or belongs to a different org.
    FileTooLargeError
        ``len(file_bytes) > MAX_FILE_BYTES``.
    InvalidJSONLError
        Any line cannot be decoded as UTF-8 or parsed as JSON (propagated
        from :func:`~app.utils.jsonl.parse_jsonl`).
    EmptyDatasetError
        The file contained zero data rows (blank lines don't count).
    TooManyRowsError
        The file contained more than ``MAX_ROWS`` rows.
    RowValidationError
        A row is valid JSON but fails :class:`~app.schemas.dataset.DatasetRow`
        schema validation (e.g. missing ``input`` or ``expected``).

    Implementation notes
    --------------------
    Step 4 (hash lookup) and step 10 (insert) together implement a
    *race-safe* idempotency check:

    * Step 4 is the fast path: if the hash already exists we avoid any parse
      or insert work.
    * Step 10's ``except IntegrityError`` is the slow path: a concurrent
      request may have inserted the same hash between step 4 and step 10.
      Instead of surfacing a database error we roll back the failed
      transaction, re-fetch the winning row by hash, and return it as a
      duplicate.  This turns a potential 500 into a correct 200.
    """
    # Step 1 — verify dataset exists and belongs to the caller's org
    dataset = await _repo.get_dataset(db, dataset_id=dataset_id, org_id=org_id)
    if dataset is None:
        raise DatasetNotFoundError(
            f"Dataset '{dataset_id}' not found.",
            details={"dataset_id": str(dataset_id)},
        )

    # Step 2 — file-size guard (cheap, before any parsing)
    if len(file_bytes) > MAX_FILE_BYTES:
        raise FileTooLargeError(
            f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit "
            f"({len(file_bytes)} bytes received).",
            details={"max_bytes": MAX_FILE_BYTES, "received_bytes": len(file_bytes)},
        )

    # Step 3 — hash the raw bytes (before any parsing; hash = identity of the file)
    content_hash = sha256_hex(file_bytes)

    # Step 4 — idempotency fast-path: same file already stored?
    existing = await _repo.get_version_by_hash(
        db, dataset_id=dataset_id, content_hash=content_hash
    )
    if existing is not None:
        return existing, True

    # Step 5 — parse JSONL; InvalidJSONLError propagates to caller unchanged
    raw_rows: list[dict[str, Any]] = parse_jsonl(file_bytes)

    # Step 6 — empty file guard (blank-only files reach here with an empty list)
    if len(raw_rows) == 0:
        raise EmptyDatasetError(
            "The uploaded file contains no data rows.",
        )

    # Step 7 — row count guard
    if len(raw_rows) > MAX_ROWS:
        raise TooManyRowsError(
            f"File contains {len(raw_rows)} rows; maximum is {MAX_ROWS}.",
            details={"max_rows": MAX_ROWS, "received_rows": len(raw_rows)},
        )

    # Step 8 — validate each row against DatasetRow schema
    validated_rows: list[DatasetRow] = []
    for idx, raw in enumerate(raw_rows, start=1):
        try:
            validated_rows.append(DatasetRow.model_validate(raw))
        except PydanticValidationError as exc:
            raise RowValidationError(
                line_number=idx,
                reason=str(exc),
            ) from exc

    # Step 9 — assign the next version number
    latest = await _repo.get_latest_version_number(db, dataset_id=dataset_id)
    new_number = (latest or 0) + 1

    # Step 10 — insert; guard against a concurrent insert of the same hash.
    #
    # Race scenario: between step 4 (hash lookup → None) and this insert,
    # another request may have committed an identical file.  The unique
    # constraint on (dataset_id, content_hash) will reject our INSERT with an
    # IntegrityError.  We roll back, re-fetch the row the winning request
    # inserted, and return it as a duplicate rather than surfacing a 500.
    try:
        version = await _repo.create_version(
            db,
            dataset_id=dataset_id,
            version_number=new_number,
            content_hash=content_hash,
            row_count=len(validated_rows),
            rows=[r.model_dump() for r in validated_rows],
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # The winning concurrent request already committed this hash — fetch it.
        existing = await _repo.get_version_by_hash(
            db, dataset_id=dataset_id, content_hash=content_hash
        )
        return existing, True  # type: ignore[return-value]

    return version, False
