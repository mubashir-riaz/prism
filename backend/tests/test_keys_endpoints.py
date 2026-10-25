"""Integration tests for API keys endpoints: creation, listing, revocation, and cross-org access protection."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName, UserRole
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService
from tests.conftest import SeededOrg


@pytest.mark.asyncio
async def test_create_key_returns_one_time_plaintext(
    auth_client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """POST /v1/keys returns 201 with plaintext_key present in response."""
    proj_svc = ProjectService(db_session)
    project = await proj_svc.create_project(
        ProjectCreate(
            organization_id=seeded_org.org_id,
            name="Key Endpoint Proj",
            slug=f"key-ep-proj-{uuid.uuid4().hex[:6]}",
        )
    )
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    payload = {
        "project_id": str(project.id),
        "environment_id": str(dev_env.id),
        "name": "Endpoint Test Key",
    }

    response = await auth_client.post("/v1/keys", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "plaintext_key" in data
    assert data["plaintext_key"].startswith(f"prism_{dev_env.name.value}_")
    assert data["name"] == "Endpoint Test Key"
    assert data["key_prefix"] in data["plaintext_key"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_keys_never_exposes_hashed_key_or_plaintext(
    auth_client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """GET /v1/keys returns key metadata, omitting hashed_key and plaintext_key."""
    proj_svc = ProjectService(db_session)
    project = await proj_svc.create_project(
        ProjectCreate(
            organization_id=seeded_org.org_id,
            name="List Keys Proj",
            slug=f"list-keys-proj-{uuid.uuid4().hex[:6]}",
        )
    )
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    create_resp = await auth_client.post(
        "/v1/keys",
        json={
            "project_id": str(project.id),
            "environment_id": str(dev_env.id),
            "name": "Key To List",
        },
    )
    assert create_resp.status_code == 201
    plaintext = create_resp.json()["plaintext_key"]

    list_resp = await auth_client.get(f"/v1/keys?project_id={project.id}")
    assert list_resp.status_code == 200

    keys = list_resp.json()
    assert len(keys) >= 1

    for k in keys:
        assert "hashed_key" not in k
        assert "plaintext_key" not in k
        assert "plaintext" not in k
        # Ensure the raw plaintext string never appears anywhere in the serialized payload
        assert plaintext not in str(k)


@pytest.mark.asyncio
async def test_revoke_key_subsequent_authenticate_fails(
    auth_client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """DELETE /v1/keys/{id} revokes the key so subsequent authentication attempts fail."""
    proj_svc = ProjectService(db_session)
    project = await proj_svc.create_project(
        ProjectCreate(
            organization_id=seeded_org.org_id,
            name="Revoke Key Proj",
            slug=f"revoke-key-proj-{uuid.uuid4().hex[:6]}",
        )
    )
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    create_resp = await auth_client.post(
        "/v1/keys",
        json={
            "project_id": str(project.id),
            "environment_id": str(dev_env.id),
            "name": "Key To Revoke",
        },
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    key_id = created_data["id"]
    plaintext = created_data["plaintext_key"]

    # Key is valid before revocation
    key_svc = APIKeyService(db_session)
    assert await key_svc.authenticate(plaintext) is not None

    # Revoke key via endpoint
    revoke_resp = await auth_client.delete(f"/v1/keys/{key_id}")
    assert revoke_resp.status_code == 200

    revoked_data = revoke_resp.json()
    assert revoked_data["is_active"] is False
    assert revoked_data["revoked_at"] is not None

    # Subsequent authenticate via service must return None
    assert await key_svc.authenticate(plaintext) is None


@pytest.mark.asyncio
async def test_cross_org_access_is_prevented(
    auth_client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """Callers from Org A cannot create, list, or revoke API keys for Org B's projects."""
    org_repo = OrganizationRepository(db_session)
    proj_svc = ProjectService(db_session)
    key_svc = APIKeyService(db_session)

    # Create Organization B and project
    org_b = await org_repo.create(
        name="Org B",
        slug=f"org-b-{uuid.uuid4().hex[:6]}",
    )
    proj_b = await proj_svc.create_project(
        ProjectCreate(
            organization_id=org_b.id,
            name="Org B Project",
            slug=f"org-b-proj-{uuid.uuid4().hex[:6]}",
        )
    )
    dev_env_b = next(e for e in proj_b.environments if e.name == EnvironmentName.DEV)
    key_b, _ = await key_svc.create_api_key(
        project_id=proj_b.id,
        environment_id=dev_env_b.id,
        name="Org B Key",
    )
    await db_session.commit()

    # auth_client belongs to seeded_org (Org A)

    # 1. Org A attempts to create a key in Org B's project -> blocked (401/403/404)
    create_attempt = await auth_client.post(
        "/v1/keys",
        json={
            "project_id": str(proj_b.id),
            "environment_id": str(dev_env_b.id),
            "name": "Malicious Key",
        },
    )
    assert create_attempt.status_code in (401, 403, 404)

    # 2. Org A attempts to list keys for Org B's project -> blocked (401/403/404)
    list_attempt = await auth_client.get(f"/v1/keys?project_id={proj_b.id}")
    assert list_attempt.status_code in (401, 403, 404)

    # 3. Org A attempts to revoke Org B's key -> blocked (401/403/404)
    revoke_attempt = await auth_client.delete(f"/v1/keys/{key_b.id}")
    assert revoke_attempt.status_code in (401, 403, 404)


@pytest.mark.asyncio
async def test_api_key_headers_fixture_authenticates(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """api_key_headers fixture provides a valid X-API-Key that authenticates via APIKeyService."""
    assert "X-API-Key" in api_key_headers
    plaintext = api_key_headers["X-API-Key"]
    assert plaintext.startswith("prism_dev_")

    service = APIKeyService(db_session)
    authenticated_key = await service.authenticate(plaintext)
    assert authenticated_key is not None
    assert authenticated_key.is_active is True
