"""Tests for TraceService: create_trace, get_trace_for_user, list_traces_for_user."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.models.enums import EnvironmentName
from app.models.organization import Organization
from app.models.project import Project
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.project import ProjectCreate
from app.schemas.trace import TraceIn
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService
from app.services.trace_service import TraceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    repo = OrganizationRepository(session)
    return await repo.create(name=slug.replace("-", " ").title(), slug=slug)


async def _make_project(session: AsyncSession, org: Organization, slug: str) -> Project:
    svc = ProjectService(session)
    return await svc.create_project(
        ProjectCreate(organization_id=org.id, name=slug, slug=slug)
    )


def _trace_payload(**overrides) -> TraceIn:
    """Return a minimal valid TraceIn instance with optional overrides."""
    base = {
        "feature": "chat",
        "model": "gpt-4o",
        "prompt": "Hello",
        "completion": "Hi",
        "prompt_tokens": 5,
        "completion_tokens": 3,
    }
    base.update(overrides)
    return TraceIn(**base)


# ---------------------------------------------------------------------------
# create_trace — tenant context always from api_key, never payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_trace_schema_rejects_organization_id_in_payload() -> None:
    """TraceIn (extra='forbid') rejects organization_id in payload — client cannot inject tenant context."""
    with pytest.raises(ValueError):
        TraceIn(
            feature="x",
            model="gpt-4o",
            prompt="p",
            completion="c",
            organization_id="00000000-0000-0000-0000-000000000000",  # type: ignore[call-arg]
        )


@pytest.mark.asyncio
async def test_create_trace_schema_rejects_project_id_in_payload() -> None:
    """TraceIn rejects project_id field — tenant scope must come from the authenticated key."""
    with pytest.raises(ValueError):
        TraceIn(
            feature="x",
            model="gpt-4o",
            prompt="p",
            completion="c",
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[call-arg]
        )


@pytest.mark.asyncio
async def test_create_trace_derives_context_from_api_key(db_session: AsyncSession) -> None:
    """create_trace sets org/project/env/api_key_id from the API key, not from any payload field."""
    org = await _make_org(db_session, "trace-svc-ctx-org")
    project = await _make_project(db_session, org, "trace-svc-ctx-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="ctx-key",
    )

    svc = TraceService(db_session)
    trace = await svc.create_trace(api_key=api_key, payload=_trace_payload())

    # All FK values come from the API key — never from the payload
    assert trace.organization_id == org.id
    assert trace.project_id == project.id
    assert trace.environment_id == dev_env.id
    assert trace.api_key_id == api_key.id


@pytest.mark.asyncio
async def test_create_trace_all_payload_fields_persisted(db_session: AsyncSession) -> None:
    """create_trace persists all payload fields correctly."""
    org = await _make_org(db_session, "trace-svc-fields-org")
    project = await _make_project(db_session, org, "trace-svc-fields-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="fields-key",
    )

    payload = _trace_payload(
        feature="summarise",
        model="claude-3-5-sonnet",
        prompt="Summarise this",
        completion="Summary here",
        prompt_tokens=15,
        completion_tokens=8,
        latency_ms=320,
        cost_usd=Decimal("0.000250"),
        prompt_version="v2",
        request_id="req-abc-123",
        metadata_json={"env": "test"},
    )

    svc = TraceService(db_session)
    trace = await svc.create_trace(api_key=api_key, payload=payload)

    assert trace.feature == "summarise"
    assert trace.model == "claude-3-5-sonnet"
    assert trace.prompt == "Summarise this"
    assert trace.completion == "Summary here"
    assert trace.prompt_tokens == 15
    assert trace.completion_tokens == 8
    assert trace.total_tokens == 23
    assert trace.latency_ms == 320
    assert float(trace.cost_usd) == pytest.approx(0.000250)
    assert trace.prompt_version == "v2"
    assert trace.request_id == "req-abc-123"
    assert trace.metadata_json == {"env": "test"}


# ---------------------------------------------------------------------------
# create_trace — audit event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_trace_writes_audit_event(db_session: AsyncSession) -> None:
    """create_trace emits an AuditLog entry with resource_type='trace'."""
    org = await _make_org(db_session, "trace-svc-audit-org")
    project = await _make_project(db_session, org, "trace-svc-audit-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="audit-key",
    )

    svc = TraceService(db_session)
    trace = await svc.create_trace(api_key=api_key, payload=_trace_payload(feature="audit-test"))

    audit_repo = AuditLogRepository(db_session)
    logs, total = await audit_repo.list_by_resource(
        resource_type="trace",
        resource_id=trace.id,
    )

    assert total >= 1
    log = logs[0]
    assert log.resource_type == "trace"
    assert log.resource_id == trace.id
    assert log.organization_id == org.id
    assert log.metadata_json["feature"] == "audit-test"
    assert "model" in log.metadata_json


# ---------------------------------------------------------------------------
# get_trace_for_user — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trace_for_user_returns_own_org_trace(db_session: AsyncSession) -> None:
    """get_trace_for_user returns the trace when it belongs to the user's org."""
    from app.repositories.user_repository import UserRepository
    from app.core.security import hash_password
    from app.models.enums import UserRole

    org = await _make_org(db_session, "trace-svc-get-org")
    project = await _make_project(db_session, org, "trace-svc-get-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="get-key",
    )

    svc = TraceService(db_session)
    created = await svc.create_trace(api_key=api_key, payload=_trace_payload())

    # Create a user in the same org
    user_repo = UserRepository(db_session)
    user = await user_repo.create(
        organization_id=org.id,
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.MEMBER,
    )
    await db_session.commit()

    fetched = await svc.get_trace_for_user(trace_id=created.id, user=user)
    assert fetched.id == created.id


# ---------------------------------------------------------------------------
# get_trace_for_user — cross-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trace_for_user_cross_org_raises_not_found(db_session: AsyncSession) -> None:
    """get_trace_for_user raises NotFoundError when trace belongs to a different org."""
    from app.repositories.user_repository import UserRepository
    from app.core.security import hash_password
    from app.models.enums import UserRole

    # Org A creates a trace
    org_a = await _make_org(db_session, "trace-svc-iso-org-a")
    project_a = await _make_project(db_session, org_a, "trace-svc-iso-proj-a")
    dev_env_a = next(e for e in project_a.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key_a, _ = await key_svc.create_api_key(
        project_id=project_a.id,
        environment_id=dev_env_a.id,
        name="iso-key-a",
    )

    svc = TraceService(db_session)
    trace_a = await svc.create_trace(api_key=api_key_a, payload=_trace_payload())

    # Org B user tries to read Org A's trace
    org_b = await _make_org(db_session, "trace-svc-iso-org-b")
    user_repo = UserRepository(db_session)
    user_b = await user_repo.create(
        organization_id=org_b.id,
        email=f"user-b-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.MEMBER,
    )
    await db_session.commit()

    with pytest.raises(NotFoundError, match="trace not found"):
        await svc.get_trace_for_user(trace_id=trace_a.id, user=user_b)


@pytest.mark.asyncio
async def test_get_trace_for_user_nonexistent_raises_not_found(db_session: AsyncSession) -> None:
    """get_trace_for_user raises NotFoundError for a UUID that doesn't exist.

    The error message must be identical to the cross-org case to prevent
    information leakage about which UUIDs are valid in other orgs.
    """
    from app.repositories.user_repository import UserRepository
    from app.core.security import hash_password
    from app.models.enums import UserRole

    org = await _make_org(db_session, "trace-svc-miss-org")
    user_repo = UserRepository(db_session)
    user = await user_repo.create(
        organization_id=org.id,
        email=f"miss-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.MEMBER,
    )
    await db_session.commit()

    nonexistent_id = uuid.uuid4()
    svc = TraceService(db_session)
    with pytest.raises(NotFoundError, match="trace not found"):
        await svc.get_trace_for_user(trace_id=nonexistent_id, user=user)


# ---------------------------------------------------------------------------
# list_traces_for_user — project ownership check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_wrong_org_raises_not_found(db_session: AsyncSession) -> None:
    """list_traces_for_user raises NotFoundError when project belongs to another org."""
    from app.repositories.user_repository import UserRepository
    from app.core.security import hash_password
    from app.models.enums import UserRole

    org_a = await _make_org(db_session, "trace-svc-list-iso-a")
    project_a = await _make_project(db_session, org_a, "trace-svc-list-iso-proj-a")

    org_b = await _make_org(db_session, "trace-svc-list-iso-b")
    user_repo = UserRepository(db_session)
    user_b = await user_repo.create(
        organization_id=org_b.id,
        email=f"list-b-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.MEMBER,
    )
    await db_session.commit()

    svc = TraceService(db_session)
    with pytest.raises(NotFoundError, match="trace not found"):
        await svc.list_traces_for_user(
            user=user_b,
            project_id=project_a.id,
            limit=10,
            offset=0,
        )
