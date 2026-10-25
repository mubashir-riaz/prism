"""Unit tests for audit logging integration across AuthService, APIKeyService, and AuditService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.exceptions import AuthError
from app.models.api_key import APIKey
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, EnvironmentName, UserRole
from app.models.environment import Environment
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.auth import RegisterRequest
from app.services.api_key_service import APIKeyService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService


def _dummy_user(
    role: UserRole = UserRole.MEMBER,
    email: str = "audit_user@example.com",
) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email=email,
        full_name="Audit Test User",
        role=role,
        is_active=True,
        hashed_password="some_argon2_or_hash",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# AuthService.register audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_service_register_emits_audit_record() -> None:
    """AuthService.register emits AuditAction.CREATE for resource_type='user' with ip/ua."""
    mock_session = MagicMock()
    service = AuthService(mock_session)

    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Acme", slug="acme")
    service.org_repo.get_by_slug = AsyncMock(return_value=org)
    service.user_repo.get_by_email_in_org = AsyncMock(return_value=None)

    created_user = _dummy_user()
    created_user.organization_id = org_id
    service.user_repo.create = AsyncMock(return_value=created_user)

    # Mock transaction context manager
    service.user_repo.transaction = MagicMock()
    service.user_repo.transaction.return_value.__aenter__ = AsyncMock()
    service.user_repo.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock AuditService.record
    service.audit_service.record = AsyncMock()

    payload = RegisterRequest(
        email="newuser@example.com",
        password="strongpassword123",
        organization_slug="acme",
        role=UserRole.MEMBER,
    )

    result = await service.register(payload, ip="192.168.1.100", ua="TestBrowser/1.0")

    assert result.id == created_user.id
    service.audit_service.record.assert_awaited_once_with(
        org_id=org_id,
        actor_id=created_user.id,
        action=AuditAction.CREATE,
        resource_type="user",
        resource_id=created_user.id,
        metadata={"email": "newuser@example.com", "role": "member"},
        ip="192.168.1.100",
        ua="TestBrowser/1.0",
    )


# ---------------------------------------------------------------------------
# AuthService.authenticate audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_service_authenticate_success_emits_audit_login() -> None:
    """AuthService.authenticate emits AuditAction.LOGIN on successful authentication."""
    mock_session = MagicMock()
    service = AuthService(mock_session)

    user = _dummy_user()
    service.user_repo.get_by_email = AsyncMock(return_value=user)
    service.user_repo.update = AsyncMock(return_value=user)

    # Mock transaction context manager
    service.user_repo.transaction = MagicMock()
    service.user_repo.transaction.return_value.__aenter__ = AsyncMock()
    service.user_repo.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

    service.audit_service.record = AsyncMock()

    with patch("app.services.auth_service.verify_password", return_value=True):
        authenticated = await service.authenticate(
            email=user.email,
            password="validpassword",
            ip="10.0.0.5",
            ua="TestClient/2.0",
        )

        assert authenticated.id == user.id
        service.audit_service.record.assert_awaited_once_with(
            org_id=user.organization_id,
            actor_id=user.id,
            action=AuditAction.LOGIN,
            resource_type="user",
            resource_id=user.id,
            metadata={"email": user.email},
            ip="10.0.0.5",
            ua="TestClient/2.0",
        )


@pytest.mark.asyncio
async def test_auth_service_authenticate_failure_does_not_audit() -> None:
    """AuthService.authenticate does NOT emit audit log when credentials fail."""
    mock_session = MagicMock()
    service = AuthService(mock_session)

    service.user_repo.get_by_email = AsyncMock(return_value=None)
    service.user_repo.transaction = MagicMock()
    service.user_repo.transaction.return_value.__aenter__ = AsyncMock()
    service.user_repo.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

    service.audit_service.record = AsyncMock()

    with pytest.raises(AuthError):
        await service.authenticate(
            email="wrong@example.com",
            password="wrongpassword",
            ip="10.0.0.5",
            ua="TestClient/2.0",
        )

    service.audit_service.record.assert_not_called()


# ---------------------------------------------------------------------------
# APIKeyService.create_api_key audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_key_service_create_emits_audit_key_created() -> None:
    """APIKeyService.create_api_key emits AuditAction.KEY_CREATED and forwards ip/ua."""
    mock_session = MagicMock()
    service = APIKeyService(mock_session)

    project_id = uuid.uuid4()
    org_id = uuid.uuid4()
    env_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    mock_project = Project(id=project_id, organization_id=org_id, name="Prism Project", slug="prism-proj")
    mock_env = Environment(id=env_id, project_id=project_id, name=EnvironmentName.DEV)
    mock_env.project = mock_project

    mock_exec_result = MagicMock()
    mock_exec_result.scalars.return_value.first.return_value = mock_env
    mock_session.execute = AsyncMock(return_value=mock_exec_result)

    key_record = APIKey(
        id=uuid.uuid4(),
        project_id=project_id,
        environment_id=env_id,
        name="test-key",
        key_prefix="prism_dev_123456789012",
        hashed_key="hashed_value",
        is_active=True,
    )
    service.repo.create = AsyncMock(return_value=key_record)
    service.repo.transaction = MagicMock()
    service.repo.transaction.return_value.__aenter__ = AsyncMock()
    service.repo.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

    service.audit_service.record = AsyncMock()

    with patch(
        "app.services.api_key_service.generate_api_key",
        return_value=("prism_dev_dummy_plain", "prism_dev_123456789012", "hashed_value"),
    ):
        record, plaintext = await service.create_api_key(
            project_id=project_id,
            environment_id=env_id,
            name="test-key",
            actor_user_id=actor_id,
            ip="172.16.0.1",
            ua="CLI/1.0",
        )

    assert record.id == key_record.id
    service.audit_service.record.assert_awaited_once_with(
        org_id=org_id,
        actor_id=actor_id,
        action=AuditAction.KEY_CREATED,
        resource_type="api_key",
        resource_id=key_record.id,
        metadata={"key_prefix": "prism_dev_123456789012", "environment": "dev", "name": "test-key"},
        ip="172.16.0.1",
        ua="CLI/1.0",
    )


# ---------------------------------------------------------------------------
# APIKeyService.revoke_api_key audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_key_service_revoke_emits_audit_key_revoked() -> None:
    """APIKeyService.revoke_api_key emits AuditAction.KEY_REVOKED and forwards ip/ua."""
    mock_session = MagicMock()
    service = APIKeyService(mock_session)

    key_id = uuid.uuid4()
    project_id = uuid.uuid4()
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    mock_project = Project(id=project_id, organization_id=org_id, name="Prism Project", slug="prism-proj")
    key = APIKey(
        id=key_id,
        project_id=project_id,
        environment_id=uuid.uuid4(),
        name="key-to-revoke",
        key_prefix="prism_dev_abcdef123456",
        hashed_key="hashed",
        is_active=True,
    )
    key.project = mock_project

    mock_exec_result = MagicMock()
    mock_exec_result.scalars.return_value.first.return_value = key
    mock_session.execute = AsyncMock(return_value=mock_exec_result)

    revoked_key = APIKey(
        id=key_id,
        project_id=project_id,
        environment_id=key.environment_id,
        name=key.name,
        key_prefix=key.key_prefix,
        hashed_key=key.hashed_key,
        is_active=False,
        revoked_at=datetime.now(timezone.utc),
    )
    service.repo.update = AsyncMock(return_value=revoked_key)
    service.repo.transaction = MagicMock()
    service.repo.transaction.return_value.__aenter__ = AsyncMock()
    service.repo.transaction.return_value.__aexit__ = AsyncMock(return_value=None)

    service.audit_service.record = AsyncMock()

    result = await service.revoke_api_key(
        id=key_id,
        actor_user_id=actor_id,
        ip="192.168.0.20",
        ua="AdminDashboard/1.0",
    )

    assert result.is_active is False
    service.audit_service.record.assert_awaited_once_with(
        org_id=org_id,
        actor_id=actor_id,
        action=AuditAction.KEY_REVOKED,
        resource_type="api_key",
        resource_id=key_id,
        metadata={"key_prefix": key.key_prefix, "name": key.name},
        ip="192.168.0.20",
        ua="AdminDashboard/1.0",
    )


# ---------------------------------------------------------------------------
# AuditService and AuditLogRepository list_for_resource / list_by_resource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_service_list_for_resource() -> None:
    """AuditService.list_for_resource delegates to AuditLogRepository.list_by_resource."""
    mock_repo = MagicMock(spec=AuditLogRepository)
    dummy_logs = [MagicMock(spec=AuditLog)]
    mock_repo.list_by_resource = AsyncMock(return_value=(dummy_logs, 1))

    svc = AuditService(mock_repo)
    res_id = uuid.uuid4()
    items, total = await svc.list_for_resource("user", res_id, offset=5, limit=25)

    assert items == dummy_logs
    assert total == 1
    mock_repo.list_by_resource.assert_awaited_once_with(
        resource_type="user",
        resource_id=res_id,
        offset=5,
        limit=25,
    )


@pytest.mark.asyncio
async def test_audit_repo_list_by_resource_passes_parsed_filters() -> None:
    """AuditLogRepository.list_by_resource converts string UUID and invokes self.list()."""
    mock_session = MagicMock()
    repo = AuditLogRepository(mock_session)

    res_id = uuid.uuid4()
    repo.list = AsyncMock(return_value=([], 0))

    await repo.list_by_resource(resource_type="user", resource_id=str(res_id), offset=0, limit=10)

    repo.list.assert_awaited_once_with(
        offset=0,
        limit=10,
        filters={"resource_type": "user", "resource_id": res_id},
    )
