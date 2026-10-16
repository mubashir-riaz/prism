"""Tests for AuditLog: append-only enforcement and metadata JSONB round-trips."""

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.models.organization import Organization
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.organization_repository import OrganizationRepository
from app.services.audit_service import AuditService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    repo = OrganizationRepository(session)
    return await repo.create(name=slug.replace("-", " ").title(), slug=slug)


async def _record_event(
    session: AsyncSession,
    org: Organization,
    action: AuditAction = AuditAction.CREATE,
    resource_type: str = "project",
    metadata: dict | None = None,
) -> AuditLog:
    svc = AuditService(session)
    return await svc.record(
        org_id=org.id,
        actor_id=None,
        action=action,
        resource_type=resource_type,
        resource_id=uuid.uuid4(),
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Append-only: update is prohibited
# ---------------------------------------------------------------------------


async def test_audit_log_update_raises_not_implemented(db_session: AsyncSession) -> None:
    """AuditLogRepository.update() always raises NotImplementedError (append-only)."""
    org = await _make_org(db_session, "audit-update-org")
    log = await _record_event(db_session, org)

    repo = AuditLogRepository(db_session)
    with pytest.raises(NotImplementedError, match="append-only"):
        await repo.update(log, metadata_json={"tampered": True})


# ---------------------------------------------------------------------------
# Append-only: delete is prohibited
# ---------------------------------------------------------------------------


async def test_audit_log_delete_raises_not_implemented(db_session: AsyncSession) -> None:
    """AuditLogRepository.delete() always raises NotImplementedError (append-only)."""
    org = await _make_org(db_session, "audit-delete-org")
    log = await _record_event(db_session, org)

    repo = AuditLogRepository(db_session)
    with pytest.raises(NotImplementedError, match="append-only"):
        await repo.delete(log)


# ---------------------------------------------------------------------------
# JSONB metadata round-trip
# ---------------------------------------------------------------------------


async def test_audit_log_metadata_empty_dict_round_trip(db_session: AsyncSession) -> None:
    """An empty metadata dict is stored and returned as an empty dict."""
    org = await _make_org(db_session, "audit-meta-empty-org")
    log = await _record_event(db_session, org, metadata={})

    assert log.metadata_json == {}


async def test_audit_log_metadata_flat_dict_round_trip(db_session: AsyncSession) -> None:
    """A flat metadata dict with various value types is faithfully round-tripped."""
    org = await _make_org(db_session, "audit-meta-flat-org")
    payload = {
        "key_name": "default-dev",
        "environment": "dev",
        "active": True,
        "count": 42,
    }
    log = await _record_event(db_session, org, metadata=payload)

    assert log.metadata_json == payload


async def test_audit_log_metadata_nested_dict_round_trip(db_session: AsyncSession) -> None:
    """Nested JSONB structures are faithfully preserved after flush."""
    org = await _make_org(db_session, "audit-meta-nested-org")
    payload = {
        "project": {
            "id": str(uuid.uuid4()),
            "slug": "demo",
            "tags": ["alpha", "beta"],
        },
        "changed_fields": ["name", "slug"],
    }
    log = await _record_event(db_session, org, metadata=payload)

    assert log.metadata_json == payload
    assert log.metadata_json["project"]["tags"] == ["alpha", "beta"]
    assert log.metadata_json["changed_fields"] == ["name", "slug"]


async def test_audit_log_metadata_unicode_round_trip(db_session: AsyncSession) -> None:
    """Unicode strings inside JSONB are stored and retrieved correctly."""
    org = await _make_org(db_session, "audit-meta-unicode-org")
    payload = {"message": "こんにちは Prism 🚀", "emoji": "✅"}
    log = await _record_event(db_session, org, metadata=payload)

    assert log.metadata_json["message"] == "こんにちは Prism 🚀"
    assert log.metadata_json["emoji"] == "✅"


# ---------------------------------------------------------------------------
# AuditService.record() stores correct fields
# ---------------------------------------------------------------------------


async def test_audit_record_stores_action(db_session: AsyncSession) -> None:
    """AuditService.record() persists the correct AuditAction value."""
    org = await _make_org(db_session, "audit-action-store-org")

    for action in (AuditAction.CREATE, AuditAction.UPDATE, AuditAction.KEY_CREATED):
        log = await _record_event(db_session, org, action=action)
        assert log.action == action


async def test_audit_record_stores_resource_type(db_session: AsyncSession) -> None:
    """AuditService.record() persists the supplied resource_type string."""
    org = await _make_org(db_session, "audit-resource-type-org")
    log = await _record_event(db_session, org, resource_type="api_key")

    assert log.resource_type == "api_key"


async def test_audit_record_with_no_actor(db_session: AsyncSession) -> None:
    """actor_user_id may be None for system-generated audit events."""
    org = await _make_org(db_session, "audit-no-actor-org")
    svc = AuditService(db_session)
    log = await svc.record(
        org_id=org.id,
        actor_id=None,
        action=AuditAction.CREATE,
        resource_type="organization",
        resource_id=org.id,
    )

    assert log.actor_user_id is None
    assert log.organization_id == org.id


# ---------------------------------------------------------------------------
# list_by_organization
# ---------------------------------------------------------------------------


async def test_list_by_organization_returns_only_org_logs(
    db_session: AsyncSession,
) -> None:
    """list_by_organization() scopes results to the specified organization."""
    org_a = await _make_org(db_session, "audit-list-org-a")
    org_b = await _make_org(db_session, "audit-list-org-b")

    await _record_event(db_session, org_a)
    await _record_event(db_session, org_a)
    await _record_event(db_session, org_b)

    repo = AuditLogRepository(db_session)
    logs_a, count_a = await repo.list_by_organization(org_a.id)
    logs_b, count_b = await repo.list_by_organization(org_b.id)

    assert count_a == 2
    assert count_b == 1
    assert all(log.organization_id == org_a.id for log in logs_a)
