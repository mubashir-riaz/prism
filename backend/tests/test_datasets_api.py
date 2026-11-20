"""
Integration tests for the /v1/datasets API endpoints.

Uses the ``client`` + ``api_key_headers`` fixtures from conftest to exercise
the full HTTP stack (FastAPI → service → repository → SQLite in-memory DB).
A second org + project + API key is created inline for cross-org isolation tests.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName, UserRole
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService
from app.core.security import hash_password
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from tests.conftest import APIKeyHeaders, SeededOrg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jsonl(*rows: dict) -> bytes:
    return b"\n".join(json.dumps(r).encode() for r in rows) + b"\n"


VALID_ROW = {"input": "What is 2+2?", "expected": "4"}
VALID_ROW_2 = {"input": "Capital of France?", "expected": "Paris"}
VALID_ROW_3 = {"input": "Sky colour?", "expected": "Blue"}

FIVE_ROWS = _make_jsonl(
    {"input": "q1", "expected": "a1"},
    {"input": "q2", "expected": "a2"},
    {"input": "q3", "expected": "a3"},
    {"input": "q4", "expected": "a4"},
    {"input": "q5", "expected": "a5"},
)
THREE_ROWS = _make_jsonl(VALID_ROW, VALID_ROW_2, VALID_ROW_3)
TWO_ROWS = _make_jsonl(VALID_ROW, VALID_ROW_2)


def _dataset_payload(project_id: uuid.UUID, name: str = "test-dataset") -> dict:
    return {"name": name, "project_id": str(project_id)}


def _upload_file(content: bytes, filename: str = "data.jsonl"):
    return {"file": (filename, content, "application/octet-stream")}


# ---------------------------------------------------------------------------
# Fixture: second org with its own API key (for cross-org tests)
# ---------------------------------------------------------------------------

@pytest.fixture
async def other_org_key(
    client: AsyncClient,
    db_session: AsyncSession,
) -> APIKeyHeaders:
    """Create a completely separate org + project + API key for isolation tests."""
    suffix = uuid.uuid4().hex[:8]

    org_repo = OrganizationRepository(db_session)
    user_repo = UserRepository(db_session)

    org = await org_repo.create(name=f"Other Org {suffix}", slug=f"other-{suffix}")
    owner = await user_repo.create(
        organization_id=org.id,
        email=f"other_{suffix}@test.com",
        hashed_password=hash_password("Password123!"),
        full_name="Other Owner",
        role=UserRole.OWNER,
        is_active=True,
    )
    await db_session.commit()

    proj_svc = ProjectService(db_session)
    project = await proj_svc.create_project(
        ProjectCreate(
            organization_id=org.id,
            name=f"Other Project {suffix}",
            slug=f"other-proj-{suffix}",
        )
    )
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    record, plaintext = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name=f"other-key-{suffix}",
        actor_user_id=owner.id,
    )
    await db_session.commit()

    return APIKeyHeaders(
        headers={"X-API-Key": plaintext},
        key_record=record,
        plaintext=plaintext,
        project=project,
        environment=dev_env,
    )


# ---------------------------------------------------------------------------
# POST /v1/datasets — create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_dataset_returns_201(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
):
    resp = await client.post(
        "/v1/datasets",
        json=_dataset_payload(api_key_headers.project.id),
        headers=dict(api_key_headers),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-dataset"
    assert "id" in data
    assert "org_id" in data
    assert data["project_id"] == str(api_key_headers.project.id)


@pytest.mark.asyncio
async def test_post_dataset_duplicate_name_returns_409(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
):
    payload = _dataset_payload(api_key_headers.project.id, name="dup-dataset")
    headers = dict(api_key_headers)

    resp1 = await client.post("/v1/datasets", json=payload, headers=headers)
    assert resp1.status_code == 201

    resp2 = await client.post("/v1/datasets", json=payload, headers=headers)
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# GET /v1/datasets — list (org-scoped)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_datasets_returns_only_caller_org_datasets(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    other_org_key: APIKeyHeaders,
):
    # Create one dataset for each org
    await client.post(
        "/v1/datasets",
        json=_dataset_payload(api_key_headers.project.id, name="org-a-ds"),
        headers=dict(api_key_headers),
    )
    await client.post(
        "/v1/datasets",
        json=_dataset_payload(other_org_key.project.id, name="org-b-ds"),
        headers=dict(other_org_key),
    )

    # Org A should only see its own dataset
    resp = await client.get("/v1/datasets", headers=dict(api_key_headers))
    assert resp.status_code == 200
    names = [ds["name"] for ds in resp.json()]
    assert "org-a-ds" in names
    assert "org-b-ds" not in names


# ---------------------------------------------------------------------------
# POST /v1/datasets/{id}/versions — upload
# ---------------------------------------------------------------------------

@pytest.fixture
async def dataset_id(client: AsyncClient, api_key_headers: APIKeyHeaders) -> uuid.UUID:
    resp = await client.post(
        "/v1/datasets",
        json=_dataset_payload(api_key_headers.project.id, name="upload-test"),
        headers=dict(api_key_headers),
    )
    return uuid.UUID(resp.json()["id"])


@pytest.mark.asyncio
async def test_upload_valid_jsonl_returns_201_not_duplicate_version_1(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    dataset_id: uuid.UUID,
):
    resp = await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=dict(api_key_headers),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["duplicate"] is False
    assert data["version_number"] == 1
    assert data["row_count"] == 3


@pytest.mark.asyncio
async def test_upload_same_file_returns_201_duplicate_true_version_1(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    dataset_id: uuid.UUID,
):
    headers = dict(api_key_headers)
    await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=headers,
    )
    resp = await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["duplicate"] is True
    assert data["version_number"] == 1


@pytest.mark.asyncio
async def test_upload_different_content_creates_version_2(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    dataset_id: uuid.UUID,
):
    headers = dict(api_key_headers)
    await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=headers,
    )
    resp = await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(TWO_ROWS),
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["version_number"] == 2


@pytest.mark.asyncio
async def test_upload_invalid_line_3_returns_400_with_line_number(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    dataset_id: uuid.UUID,
):
    bad_jsonl = (
        b'{"input": "q1", "expected": "a1"}\n'
        b'{"input": "q2", "expected": "a2"}\n'
        b"this is not json\n"
    )
    resp = await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(bad_jsonl),
        headers=dict(api_key_headers),
    )
    assert resp.status_code == 400
    assert "line 3" in resp.json()["detail"].lower() or "3" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /v1/datasets/{id}/versions — list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_versions_returns_all_versions(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    dataset_id: uuid.UUID,
):
    headers = dict(api_key_headers)
    await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=headers,
    )
    await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(TWO_ROWS),
        headers=headers,
    )

    resp = await client.get(f"/v1/datasets/{dataset_id}/versions", headers=headers)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 1
    assert versions[1]["version_number"] == 2


# ---------------------------------------------------------------------------
# GET /v1/datasets/{id}/versions/{number} — detail with preview
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_version_detail_returns_rows_preview(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    dataset_id: uuid.UUID,
):
    headers = dict(api_key_headers)
    await client.post(
        f"/v1/datasets/{dataset_id}/versions",
        files=_upload_file(FIVE_ROWS),
        headers=headers,
    )

    resp = await client.get(
        f"/v1/datasets/{dataset_id}/versions/1", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_number"] == 1
    assert len(data["rows_preview"]) == 5  # all 5 rows fit within default preview_limit=10


# ---------------------------------------------------------------------------
# Cross-org isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_org_upload_to_other_org_dataset_returns_404(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    other_org_key: APIKeyHeaders,
):
    # Org A creates a dataset
    resp = await client.post(
        "/v1/datasets",
        json=_dataset_payload(api_key_headers.project.id, name="org-a-exclusive"),
        headers=dict(api_key_headers),
    )
    org_a_dataset_id = resp.json()["id"]

    # Org B tries to upload to it — must get 404, not 403
    resp = await client.post(
        f"/v1/datasets/{org_a_dataset_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=dict(other_org_key),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_get_version_detail_returns_404(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    other_org_key: APIKeyHeaders,
):
    # Org A creates a dataset and uploads a version
    resp = await client.post(
        "/v1/datasets",
        json=_dataset_payload(api_key_headers.project.id, name="org-a-ver-exclusive"),
        headers=dict(api_key_headers),
    )
    ds_id = resp.json()["id"]
    await client.post(
        f"/v1/datasets/{ds_id}/versions",
        files=_upload_file(THREE_ROWS),
        headers=dict(api_key_headers),
    )

    # Org B tries to fetch the version detail — must get 404
    resp = await client.get(
        f"/v1/datasets/{ds_id}/versions/1",
        headers=dict(other_org_key),
    )
    assert resp.status_code == 404
