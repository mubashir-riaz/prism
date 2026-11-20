"""
Unit tests for app/services/dataset_service.py.

All tests use the ``db_session`` fixture from conftest (SQLite in-memory when
Postgres is unavailable) and the ``seeded_org`` + ``api_key_for_project``
fixtures to get real org/project rows.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    DatasetNotFoundError,
    EmptyDatasetError,
    FileTooLargeError,
    RowValidationError,
    TooManyRowsError,
)
from app.models.dataset_version import DatasetVersion
from app.services import dataset_service
from app.utils.jsonl import InvalidJSONLError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jsonl(*rows: dict) -> bytes:
    """Serialize dicts to JSONL bytes."""
    return b"\n".join(json.dumps(r).encode() for r in rows) + b"\n"


VALID_ROW_1 = {"input": "What is 2+2?", "expected": "4"}
VALID_ROW_2 = {"input": "Capital of France?", "expected": "Paris"}
VALID_ROW_3 = {"input": "Sky colour?", "expected": "Blue"}

THREE_ROWS = _make_jsonl(VALID_ROW_1, VALID_ROW_2, VALID_ROW_3)
TWO_ROWS = _make_jsonl(VALID_ROW_1, VALID_ROW_2)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def dataset(db_session: AsyncSession, seeded_org, api_key_for_project):
    """Create and return a Dataset under the seeded org/project."""
    ds = await dataset_service.create_dataset(
        db_session,
        org_id=seeded_org.org_id,
        project_id=api_key_for_project.project.id,
        name="eval-set-1",
    )
    return ds


# ---------------------------------------------------------------------------
# Test: create_dataset
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_dataset_returns_correct_fields(
    db_session: AsyncSession,
    seeded_org,
    api_key_for_project,
):
    ds = await dataset_service.create_dataset(
        db_session,
        org_id=seeded_org.org_id,
        project_id=api_key_for_project.project.id,
        name="my-dataset",
    )

    assert ds.id is not None
    assert ds.org_id == seeded_org.org_id
    assert ds.project_id == api_key_for_project.project.id
    assert ds.name == "my-dataset"
    assert ds.created_at is not None


# ---------------------------------------------------------------------------
# Test: upload_version — first upload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_first_version_returns_version_number_1_and_not_duplicate(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    version, was_duplicate = await dataset_service.upload_version(
        db_session,
        dataset_id=dataset.id,
        org_id=seeded_org.org_id,
        file_bytes=THREE_ROWS,
    )

    assert was_duplicate is False
    assert version.version_number == 1
    assert version.row_count == 3
    assert version.dataset_id == dataset.id
    assert len(version.content_hash) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Test: upload_version — duplicate (same bytes)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_same_bytes_returns_duplicate_true_and_same_version(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    first, _ = await dataset_service.upload_version(
        db_session,
        dataset_id=dataset.id,
        org_id=seeded_org.org_id,
        file_bytes=THREE_ROWS,
    )

    second, was_duplicate = await dataset_service.upload_version(
        db_session,
        dataset_id=dataset.id,
        org_id=seeded_org.org_id,
        file_bytes=THREE_ROWS,
    )

    assert was_duplicate is True
    assert second.id == first.id
    assert second.version_number == 1

    # Confirm only one version row in the DB
    result = await db_session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id)
    )
    all_versions = result.scalars().all()
    assert len(all_versions) == 1


# ---------------------------------------------------------------------------
# Test: upload_version — different bytes → version 2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_different_bytes_creates_version_2(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    await dataset_service.upload_version(
        db_session,
        dataset_id=dataset.id,
        org_id=seeded_org.org_id,
        file_bytes=THREE_ROWS,
    )

    v2, was_duplicate = await dataset_service.upload_version(
        db_session,
        dataset_id=dataset.id,
        org_id=seeded_org.org_id,
        file_bytes=TWO_ROWS,
    )

    assert was_duplicate is False
    assert v2.version_number == 2
    assert v2.row_count == 2


# ---------------------------------------------------------------------------
# Test: invalid JSON line → InvalidJSONLError, no version created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_json_line_raises_and_no_version_inserted(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    bad_bytes = (
        b'{"input": "q", "expected": "a"}\n'
        b"this is not json\n"
    )

    with pytest.raises(InvalidJSONLError) as exc_info:
        await dataset_service.upload_version(
            db_session,
            dataset_id=dataset.id,
            org_id=seeded_org.org_id,
            file_bytes=bad_bytes,
        )

    assert exc_info.value.line_number == 2

    # No version must have been committed
    result = await db_session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id)
    )
    assert result.scalars().first() is None


# ---------------------------------------------------------------------------
# Test: row missing 'expected' → RowValidationError with correct line number
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_row_missing_expected_raises_row_validation_error(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    bad_bytes = _make_jsonl(
        {"input": "q1", "expected": "a1"},
        {"input": "q2"},  # missing 'expected' — line 2
    )

    with pytest.raises(RowValidationError) as exc_info:
        await dataset_service.upload_version(
            db_session,
            dataset_id=dataset.id,
            org_id=seeded_org.org_id,
            file_bytes=bad_bytes,
        )

    assert exc_info.value.line_number == 2


# ---------------------------------------------------------------------------
# Test: empty file → EmptyDatasetError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_file_raises_empty_dataset_error(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    with pytest.raises(EmptyDatasetError):
        await dataset_service.upload_version(
            db_session,
            dataset_id=dataset.id,
            org_id=seeded_org.org_id,
            file_bytes=b"",
        )


# ---------------------------------------------------------------------------
# Test: 10,001 rows → TooManyRowsError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_too_many_rows_raises_too_many_rows_error(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    over_limit = _make_jsonl(
        *[{"input": f"q{i}", "expected": f"a{i}"} for i in range(dataset_service.MAX_ROWS + 1)]
    )

    with pytest.raises(TooManyRowsError):
        await dataset_service.upload_version(
            db_session,
            dataset_id=dataset.id,
            org_id=seeded_org.org_id,
            file_bytes=over_limit,
        )


# ---------------------------------------------------------------------------
# Test: wrong org → DatasetNotFoundError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_against_wrong_org_raises_dataset_not_found(
    db_session: AsyncSession,
    dataset,
):
    wrong_org_id = uuid.uuid4()

    with pytest.raises(DatasetNotFoundError):
        await dataset_service.upload_version(
            db_session,
            dataset_id=dataset.id,
            org_id=wrong_org_id,
            file_bytes=THREE_ROWS,
        )


# ---------------------------------------------------------------------------
# Test: file too large → FileTooLargeError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_exceeding_size_limit_raises_file_too_large(
    db_session: AsyncSession,
    seeded_org,
    dataset,
):
    # Construct a fake payload that exceeds MAX_FILE_BYTES without actually
    # building a 10 MB JSONL string — patch the constant temporarily.
    original_limit = dataset_service.MAX_FILE_BYTES
    dataset_service.MAX_FILE_BYTES = 10  # 10 bytes for test

    try:
        with pytest.raises(FileTooLargeError):
            await dataset_service.upload_version(
                db_session,
                dataset_id=dataset.id,
                org_id=seeded_org.org_id,
                file_bytes=b"x" * 11,
            )
    finally:
        dataset_service.MAX_FILE_BYTES = original_limit
