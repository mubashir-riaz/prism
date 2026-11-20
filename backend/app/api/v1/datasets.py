"""Dataset CRUD and version upload endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key
from app.db.session import get_db
from app.exceptions import (
    DatasetNotFoundError,
    EmptyDatasetError,
    FileTooLargeError,
    RowValidationError,
    TooManyRowsError,
)
from app.models.api_key import APIKey
from app.schemas.dataset import DatasetIn, DatasetOut
from app.schemas.dataset_version import DatasetVersionDetail, DatasetVersionOut
from app.services import dataset_service
from app.utils.jsonl import InvalidJSONLError

router = APIRouter()


# ---------------------------------------------------------------------------
# Error mapping helper
# ---------------------------------------------------------------------------


def _map_service_error(exc: Exception) -> HTTPException:
    """Translate dataset service exceptions into HTTPException instances.

    Centralising this avoids repeating the same if/elif chain in every route
    and keeps the mapping easy to audit in one place.
    """
    if isinstance(exc, DatasetNotFoundError):
        # Same 404 for "not found" and "wrong org" — no existence leak.
        return HTTPException(status_code=404, detail="Dataset not found.")
    if isinstance(exc, InvalidJSONLError):
        return HTTPException(
            status_code=400,
            detail=f"Invalid JSONL at line {exc.line_number}: {exc.reason}",
        )
    if isinstance(exc, RowValidationError):
        return HTTPException(
            status_code=400,
            detail=f"Row {exc.line_number} invalid: {exc.reason}",
        )
    if isinstance(exc, EmptyDatasetError):
        return HTTPException(status_code=400, detail="Dataset is empty.")
    if isinstance(exc, TooManyRowsError):
        return HTTPException(
            status_code=413, detail="Dataset exceeds 10,000 row limit."
        )
    if isinstance(exc, FileTooLargeError):
        return HTTPException(status_code=413, detail="File exceeds 10 MB.")
    # Unexpected — re-raise so the global handler picks it up.
    raise exc


# ---------------------------------------------------------------------------
# POST /v1/datasets — create a dataset
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dataset",
    description="Create a new named dataset scoped to a project.",
)
async def create_dataset(
    payload: DatasetIn,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> DatasetOut:
    org_id: uuid.UUID = api_key.project.organization_id
    try:
        dataset = await dataset_service.create_dataset(
            db,
            org_id=org_id,
            project_id=payload.project_id,
            name=payload.name,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A dataset with this name already exists in this project.",
        )
    return DatasetOut.model_validate(dataset)


# ---------------------------------------------------------------------------
# GET /v1/datasets — list datasets
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[DatasetOut],
    status_code=status.HTTP_200_OK,
    summary="List datasets",
    description="List all datasets for the authenticated organisation, optionally filtered by project.",
)
async def list_datasets(
    project_id: uuid.UUID | None = Query(None, description="Filter by project UUID."),
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetOut]:
    org_id: uuid.UUID = api_key.project.organization_id
    datasets = await dataset_service.list_datasets(db, org_id=org_id, project_id=project_id)
    return [DatasetOut.model_validate(ds) for ds in datasets]


# ---------------------------------------------------------------------------
# POST /v1/datasets/{dataset_id}/versions — upload a new version
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a dataset version",
    description=(
        "Upload a JSONL file as a new version of the dataset. "
        "Identical files (same SHA-256) return the existing version with ``duplicate=true``."
    ),
)
async def upload_version(
    dataset_id: uuid.UUID,
    file: UploadFile = File(..., description="JSONL file — one JSON object per line."),
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> DatasetVersionOut:
    org_id: uuid.UUID = api_key.project.organization_id
    content: bytes = await file.read()
    try:
        version, was_duplicate = await dataset_service.upload_version(
            db,
            dataset_id=dataset_id,
            org_id=org_id,
            file_bytes=content,
        )
    except Exception as exc:
        raise _map_service_error(exc)

    out = DatasetVersionOut.model_validate(version)
    # `duplicate` is a synthetic flag — not stored in the DB, set here.
    out = out.model_copy(update={"duplicate": was_duplicate})
    return out


# ---------------------------------------------------------------------------
# GET /v1/datasets/{dataset_id}/versions — list all versions
# Note: declared BEFORE /{dataset_id}/versions/{version_number} so the
# more-specific parameterised path does not shadow the collection route.
# ---------------------------------------------------------------------------


@router.get(
    "/{dataset_id}/versions",
    response_model=list[DatasetVersionOut],
    status_code=status.HTTP_200_OK,
    summary="List dataset versions",
    description="Return all versions of a dataset ordered by version_number ascending.",
)
async def list_versions(
    dataset_id: uuid.UUID,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetVersionOut]:
    org_id: uuid.UUID = api_key.project.organization_id
    try:
        versions = await dataset_service.list_versions(
            db, dataset_id=dataset_id, org_id=org_id
        )
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return [DatasetVersionOut.model_validate(v) for v in versions]


# ---------------------------------------------------------------------------
# GET /v1/datasets/{dataset_id}/versions/{version_number} — version detail
# ---------------------------------------------------------------------------


@router.get(
    "/{dataset_id}/versions/{version_number}",
    response_model=DatasetVersionDetail,
    status_code=status.HTTP_200_OK,
    summary="Get dataset version detail",
    description="Return full metadata and a row preview for a specific version.",
)
async def get_version_detail(
    dataset_id: uuid.UUID,
    version_number: int,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> DatasetVersionDetail:
    org_id: uuid.UUID = api_key.project.organization_id
    detail = await dataset_service.get_version_detail(
        db,
        dataset_id=dataset_id,
        version_number=version_number,
        org_id=org_id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    return detail


__all__ = ["router"]
