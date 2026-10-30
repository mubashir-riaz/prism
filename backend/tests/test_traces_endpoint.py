"""Integration tests for POST /v1/traces and GET /v1/traces/{id} endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName
from app.models.trace import Trace
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService
from app.core.security import create_access_token, hash_password
from app.models.enums import UserRole
from tests.conftest import APIKeyHeaders, SeededOrg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_body(**overrides) -> dict:
    base = {
        "feature": "search",
        "model": "gpt-4o",
        "prompt": "Hello",
        "completion": "Hi there",
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# POST /v1/traces — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_trace_returns_201_with_id_and_created_at(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces with a valid key returns 201 with id and created_at."""
    response = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers=dict(api_key_headers),
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "created_at" in data
    # Minimal receipt — must NOT include prompt/completion text
    assert "prompt" not in data
    assert "completion" not in data


@pytest.mark.asyncio
async def test_post_trace_writes_correct_fk_values_to_db(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces persists organization_id, project_id, environment_id, api_key_id correctly."""
    response = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers=dict(api_key_headers),
    )
    assert response.status_code == 201
    trace_id = uuid.UUID(response.json()["id"])

    # Fetch from DB and verify FK values
    result = await db_session.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalars().first()
    assert trace is not None

    key_record = api_key_headers.key_record
    project = api_key_headers.project
    environment = api_key_headers.environment

    assert trace.project_id == project.id
    assert trace.environment_id == environment.id
    assert trace.api_key_id == key_record.id
    # organization_id comes from the project's org
    assert trace.organization_id == project.organization_id


@pytest.mark.asyncio
async def test_post_trace_only_one_new_row_created(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces creates exactly one new Trace row."""
    project = api_key_headers.project

    before = await db_session.execute(
        select(Trace).where(Trace.project_id == project.id)
    )
    count_before = len(before.scalars().all())

    response = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers=dict(api_key_headers),
    )
    assert response.status_code == 201

    after = await db_session.execute(
        select(Trace).where(Trace.project_id == project.id)
    )
    count_after = len(after.scalars().all())

    assert count_after == count_before + 1


# ---------------------------------------------------------------------------
# POST /v1/traces — X-Request-ID header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_trace_x_request_id_echoes_client_value(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """X-Request-ID response header echoes the client-supplied request_id when provided."""
    client_request_id = "my-correlation-id-abc"
    response = await client.post(
        "/v1/traces",
        json=_valid_body(request_id=client_request_id),
        headers=dict(api_key_headers),
    )
    assert response.status_code == 201
    assert response.headers.get("x-request-id") == client_request_id


@pytest.mark.asyncio
async def test_post_trace_x_request_id_falls_back_to_trace_id(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """X-Request-ID falls back to the trace UUID when request_id is absent."""
    response = await client.post(
        "/v1/traces",
        json=_valid_body(),  # no request_id
        headers=dict(api_key_headers),
    )
    assert response.status_code == 201
    trace_id = response.json()["id"]
    assert response.headers.get("x-request-id") == trace_id


# ---------------------------------------------------------------------------
# POST /v1/traces — auth failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_trace_without_api_key_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces without X-API-Key header returns 401 with standard error body."""
    response = await client.post("/v1/traces", json=_valid_body())
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["type"] == "AuthError"


@pytest.mark.asyncio
async def test_post_trace_with_invalid_key_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces with a bogus X-API-Key returns 401."""
    response = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers={"X-API-Key": "prism_dev_invalid_key_that_does_not_exist"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "AuthError"


@pytest.mark.asyncio
async def test_post_trace_with_revoked_key_returns_401(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces with a revoked key returns 401."""
    key_svc = APIKeyService(db_session)
    await key_svc.revoke_api_key(api_key_headers.key_record.id)

    response = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers=dict(api_key_headers),
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /v1/traces — validation failures (422)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_trace_mismatched_total_tokens_returns_422(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces with mismatched total_tokens returns 422."""
    body = _valid_body(prompt_tokens=5, completion_tokens=5, total_tokens=99)
    response = await client.post(
        "/v1/traces",
        json=body,
        headers=dict(api_key_headers),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_trace_unknown_field_returns_422(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """POST /v1/traces with an unknown field returns 422 (extra='forbid')."""
    body = _valid_body()
    body["organization_id"] = str(uuid.uuid4())  # forbidden field
    response = await client.post(
        "/v1/traces",
        json=body,
        headers=dict(api_key_headers),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/traces/{id} — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trace_own_org_returns_200_with_full_body(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """GET /v1/traces/{id} with a JWT from the same org returns 200 and full TraceOut."""
    # Create a trace via POST
    post_resp = await client.post(
        "/v1/traces",
        json=_valid_body(feature="debug-test", model="gpt-4o-mini"),
        headers=dict(api_key_headers),
    )
    assert post_resp.status_code == 201
    trace_id = post_resp.json()["id"]

    # Authenticate as the org owner
    token = create_access_token(
        subject=str(seeded_org.owner.id),
        org_id=str(seeded_org.org.id),
        role=seeded_org.owner.role.value,
    )

    get_resp = await client.get(
        f"/v1/traces/{trace_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == trace_id
    assert data["feature"] == "debug-test"
    assert data["model"] == "gpt-4o-mini"
    # Full body includes prompt and completion
    assert "prompt" in data
    assert "completion" in data


# ---------------------------------------------------------------------------
# GET /v1/traces/{id} — cross-org returns 404, not 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trace_different_org_returns_404_not_403(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """GET /v1/traces/{id} with a JWT from a different org returns 404, not 403."""
    # Create a trace belonging to the api_key_headers org
    post_resp = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers=dict(api_key_headers),
    )
    assert post_resp.status_code == 201
    trace_id = post_resp.json()["id"]

    # Create a second org and user
    org_repo = OrganizationRepository(db_session)
    other_org = await org_repo.create(
        name="Other Org",
        slug=f"other-org-{uuid.uuid4().hex[:6]}",
    )
    user_repo = UserRepository(db_session)
    other_user = await user_repo.create(
        organization_id=other_org.id,
        email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.MEMBER,
    )
    await db_session.commit()

    other_token = create_access_token(
        subject=str(other_user.id),
        org_id=str(other_org.id),
        role=other_user.role.value,
    )

    get_resp = await client.get(
        f"/v1/traces/{trace_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    # Must be 404, not 403 — no information about whether the UUID exists
    assert get_resp.status_code == 404
    assert get_resp.json()["error"]["type"] == "NotFoundError"


# ---------------------------------------------------------------------------
# GET /v1/traces/{id} — auth failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trace_without_jwt_returns_401(
    client: AsyncClient,
    api_key_headers: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """GET /v1/traces/{id} without Authorization header returns 401."""
    post_resp = await client.post(
        "/v1/traces",
        json=_valid_body(),
        headers=dict(api_key_headers),
    )
    assert post_resp.status_code == 201
    trace_id = post_resp.json()["id"]

    get_resp = await client.get(f"/v1/traces/{trace_id}")
    assert get_resp.status_code == 401


@pytest.mark.asyncio
async def test_get_trace_nonexistent_uuid_returns_404(
    client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """GET /v1/traces/{id} for a non-existent UUID returns 404."""
    token = create_access_token(
        subject=str(seeded_org.owner.id),
        org_id=str(seeded_org.org.id),
        role=seeded_org.owner.role.value,
    )
    nonexistent_id = uuid.uuid4()
    response = await client.get(
        f"/v1/traces/{nonexistent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "NotFoundError"
