"""Tests for TraceRepository: list ordering, pagination, and count."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName
from app.models.organization import Organization
from app.models.project import Project
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.trace_repository import TraceRepository
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService
from app.services.trace_service import TraceService
from app.schemas.trace import TraceIn


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


def _payload(feature: str = "test") -> TraceIn:
    return TraceIn(
        feature=feature,
        model="gpt-4o",
        prompt="prompt",
        completion="completion",
        prompt_tokens=3,
        completion_tokens=2,
    )


async def _create_n_traces(
    session: AsyncSession,
    n: int,
    project: Project,
    dev_env,
    api_key,
) -> list:
    svc = TraceService(session)
    traces = []
    for i in range(n):
        t = await svc.create_trace(api_key=api_key, payload=_payload(feature=f"feat-{i}"))
        traces.append(t)
    return traces


# ---------------------------------------------------------------------------
# list_by_project — ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_project_ordered_by_created_at_desc(db_session: AsyncSession) -> None:
    """list_by_project returns traces ordered newest-first (created_at DESC)."""
    org = await _make_org(db_session, "repo-order-org")
    project = await _make_project(db_session, org, "repo-order-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="order-key",
    )

    await _create_n_traces(db_session, 3, project, dev_env, api_key)

    repo = TraceRepository(db_session)
    items, total = await repo.list_by_project(
        project_id=project.id,
        limit=10,
        offset=0,
    )

    assert total == 3
    assert len(items) == 3

    # Verify descending order
    for i in range(len(items) - 1):
        assert items[i].created_at >= items[i + 1].created_at


# ---------------------------------------------------------------------------
# list_by_project — pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_project_respects_limit(db_session: AsyncSession) -> None:
    """list_by_project returns at most `limit` items."""
    org = await _make_org(db_session, "repo-limit-org")
    project = await _make_project(db_session, org, "repo-limit-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="limit-key",
    )

    await _create_n_traces(db_session, 5, project, dev_env, api_key)

    repo = TraceRepository(db_session)
    items, total = await repo.list_by_project(
        project_id=project.id,
        limit=2,
        offset=0,
    )

    assert total == 5       # total reflects all matching rows
    assert len(items) == 2  # page contains only `limit` items


@pytest.mark.asyncio
async def test_list_by_project_respects_offset(db_session: AsyncSession) -> None:
    """list_by_project skips `offset` items."""
    org = await _make_org(db_session, "repo-offset-org")
    project = await _make_project(db_session, org, "repo-offset-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="offset-key",
    )

    await _create_n_traces(db_session, 4, project, dev_env, api_key)

    repo = TraceRepository(db_session)

    # Fetch all
    all_items, _ = await repo.list_by_project(project_id=project.id, limit=100, offset=0)
    # Fetch with offset=2
    paged_items, total = await repo.list_by_project(project_id=project.id, limit=100, offset=2)

    assert total == 4
    assert len(paged_items) == 2
    # The first item with offset=2 should match the 3rd item overall
    assert paged_items[0].id == all_items[2].id


@pytest.mark.asyncio
async def test_list_by_project_empty_project(db_session: AsyncSession) -> None:
    """list_by_project returns ([], 0) for a project with no traces."""
    org = await _make_org(db_session, "repo-empty-org")
    project = await _make_project(db_session, org, "repo-empty-proj")

    repo = TraceRepository(db_session)
    items, total = await repo.list_by_project(
        project_id=project.id,
        limit=10,
        offset=0,
    )

    assert total == 0
    assert items == []


@pytest.mark.asyncio
async def test_list_by_project_total_matches_all_rows(db_session: AsyncSession) -> None:
    """total_count in list_by_project reflects the full unfiltered row count."""
    org = await _make_org(db_session, "repo-total-org")
    project = await _make_project(db_session, org, "repo-total-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="total-key",
    )

    n = 6
    await _create_n_traces(db_session, n, project, dev_env, api_key)

    repo = TraceRepository(db_session)
    # Fetch only 2 items but total must report 6
    items, total = await repo.list_by_project(project_id=project.id, limit=2, offset=0)

    assert total == n
    assert len(items) == 2


# ---------------------------------------------------------------------------
# count_by_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_by_project_correct_after_n_inserts(db_session: AsyncSession) -> None:
    """count_by_project returns the exact number of traces inserted."""
    org = await _make_org(db_session, "repo-count-org")
    project = await _make_project(db_session, org, "repo-count-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="count-key",
    )

    repo = TraceRepository(db_session)
    assert await repo.count_by_project(project.id) == 0

    n = 7
    await _create_n_traces(db_session, n, project, dev_env, api_key)
    assert await repo.count_by_project(project.id) == n


@pytest.mark.asyncio
async def test_count_by_project_scoped_to_project(db_session: AsyncSession) -> None:
    """count_by_project counts only traces for the given project, not others."""
    org = await _make_org(db_session, "repo-scope-count-org")
    project_a = await _make_project(db_session, org, "repo-scope-count-proj-a")
    project_b = await _make_project(db_session, org, "repo-scope-count-proj-b")

    dev_env_a = next(e for e in project_a.environments if e.name == EnvironmentName.DEV)
    dev_env_b = next(e for e in project_b.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key_a, _ = await key_svc.create_api_key(
        project_id=project_a.id, environment_id=dev_env_a.id, name="scope-key-a"
    )
    api_key_b, _ = await key_svc.create_api_key(
        project_id=project_b.id, environment_id=dev_env_b.id, name="scope-key-b"
    )

    await _create_n_traces(db_session, 3, project_a, dev_env_a, api_key_a)
    await _create_n_traces(db_session, 5, project_b, dev_env_b, api_key_b)

    repo = TraceRepository(db_session)
    assert await repo.count_by_project(project_a.id) == 3
    assert await repo.count_by_project(project_b.id) == 5


# ---------------------------------------------------------------------------
# get_by_id_for_org — org scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_id_for_org_returns_own_trace(db_session: AsyncSession) -> None:
    """get_by_id_for_org returns the trace when org ID matches."""
    org = await _make_org(db_session, "repo-get-own-org")
    project = await _make_project(db_session, org, "repo-get-own-proj")
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key, _ = await key_svc.create_api_key(
        project_id=project.id, environment_id=dev_env.id, name="get-own-key"
    )

    svc = TraceService(db_session)
    trace = await svc.create_trace(api_key=api_key, payload=_payload())

    repo = TraceRepository(db_session)
    result = await repo.get_by_id_for_org(trace_id=trace.id, organization_id=org.id)
    assert result is not None
    assert result.id == trace.id


@pytest.mark.asyncio
async def test_get_by_id_for_org_returns_none_for_wrong_org(db_session: AsyncSession) -> None:
    """get_by_id_for_org returns None when org ID doesn't match (no information leakage)."""
    org_a = await _make_org(db_session, "repo-cross-org-a")
    project_a = await _make_project(db_session, org_a, "repo-cross-proj-a")
    dev_env_a = next(e for e in project_a.environments if e.name == EnvironmentName.DEV)

    key_svc = APIKeyService(db_session)
    api_key_a, _ = await key_svc.create_api_key(
        project_id=project_a.id, environment_id=dev_env_a.id, name="cross-key-a"
    )

    svc = TraceService(db_session)
    trace_a = await svc.create_trace(api_key=api_key_a, payload=_payload())

    org_b = await _make_org(db_session, "repo-cross-org-b")

    repo = TraceRepository(db_session)
    result = await repo.get_by_id_for_org(trace_id=trace_a.id, organization_id=org_b.id)
    assert result is None
