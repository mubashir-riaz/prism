"""Integration tests for auth endpoints: registration, login, enumeration prevention, and /me."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from tests.conftest import SeededOrg


@pytest.mark.asyncio
async def test_register_creates_user_and_records_audit(
    client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """POST /v1/auth/register creates a user, returns 201/200, and records an audit event."""
    payload = {
        "email": "fresh_user@example.com",
        "password": "ValidPassword123!",
        "full_name": "Fresh User",
        "organization_slug": seeded_org.org.slug,
        "role": "member",
    }

    response = await client.post("/v1/auth/register", json=payload)
    assert response.status_code in (200, 201)

    data = response.json()
    assert data["email"] == "fresh_user@example.com"
    assert data["role"] == "member"
    assert "id" in data

    # Verify user persisted in database
    user_repo = UserRepository(db_session)
    persisted_user = await user_repo.get_by_email_in_org(
        seeded_org.org_id,
        "fresh_user@example.com",
    )
    assert persisted_user is not None
    assert str(persisted_user.id) == data["id"]

    # Verify audit event recorded
    audit_repo = AuditLogRepository(db_session)
    audit_logs, count = await audit_repo.list_by_resource(
        resource_type="user",
        resource_id=persisted_user.id,
    )
    assert count >= 1
    create_log = next(log for log in audit_logs if log.action == AuditAction.CREATE)
    assert create_log.resource_type == "user"
    assert create_log.organization_id == seeded_org.org_id


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(
    client: AsyncClient,
    seeded_org: SeededOrg,
) -> None:
    """POST /v1/auth/register with an existing email in the same org returns 409 ConflictError."""
    payload = {
        "email": seeded_org.owner.email,
        "password": "Password123!",
        "full_name": "Duplicate Owner",
        "organization_slug": seeded_org.org.slug,
        "role": "member",
    }

    response = await client.post("/v1/auth/register", json=payload)
    assert response.status_code == 409

    body = response.json()
    assert "error" in body
    assert body["error"]["type"] == "ConflictError"
    assert "already registered" in body["error"]["message"].lower()


@pytest.mark.asyncio
async def test_login_success_returns_token(
    client: AsyncClient,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """POST /v1/auth/login with valid credentials returns 200, access token, and emits audit."""
    payload = {
        "email": seeded_org.owner.email,
        "password": seeded_org.password,
        "organization_slug": seeded_org.org.slug,
    }

    response = await client.post("/v1/auth/login", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"
    assert data["expires_in"] > 0

    # Verify audit event recorded
    audit_repo = AuditLogRepository(db_session)
    audit_logs, count = await audit_repo.list_by_resource(
        resource_type="user",
        resource_id=seeded_org.owner.id,
    )
    login_logs = [log for log in audit_logs if log.action == AuditAction.LOGIN]
    assert len(login_logs) >= 1


@pytest.mark.asyncio
async def test_login_wrong_password_prevents_user_enumeration(
    client: AsyncClient,
    seeded_org: SeededOrg,
) -> None:
    """POST /v1/auth/login with wrong password returns 401 with identical response to missing user."""
    # 1. Existing user with wrong password
    resp_wrong_pw = await client.post(
        "/v1/auth/login",
        json={
            "email": seeded_org.email,
            "password": "IncorrectPassword123!",
            "organization_slug": seeded_org.slug,
        },
    )
    assert resp_wrong_pw.status_code == 401
    body_wrong_pw = resp_wrong_pw.json()

    # 2. Non-existent user
    resp_missing_user = await client.post(
        "/v1/auth/login",
        json={
            "email": "nobody_exists_here@example.com",
            "password": "IncorrectPassword123!",
            "organization_slug": seeded_org.slug,
        },
    )
    assert resp_missing_user.status_code == 401
    body_missing_user = resp_missing_user.json()

    # Both must match to prevent timing/string user-enumeration attacks
    assert body_wrong_pw["error"]["type"] == body_missing_user["error"]["type"]
    assert body_wrong_pw["error"]["message"] == body_missing_user["error"]["message"]


@pytest.mark.asyncio
async def test_auth_me_with_and_without_token(
    client: AsyncClient,
    auth_client: AsyncClient,
    seeded_org: SeededOrg,
) -> None:
    """GET /v1/auth/me returns 200 with valid bearer token; 401 without or with invalid token."""
    # 1. Valid token (owner)
    resp_valid = await auth_client.get("/v1/auth/me")
    assert resp_valid.status_code == 200
    user_data = resp_valid.json()
    assert user_data["id"] == str(seeded_org.owner.id)
    assert user_data["email"] == seeded_org.owner.email
    assert user_data["role"] == "owner"

    # 2. Without token
    resp_no_token = await client.get("/v1/auth/me")
    assert resp_no_token.status_code == 401

    # 3. With invalid token
    resp_bad_token = await client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer bad.token.value"},
    )
    assert resp_bad_token.status_code == 401
