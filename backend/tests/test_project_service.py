"""Tests for ProjectService: auto-environment creation, default-env deletion guard."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, ValidationError
from app.models.enums import EnvironmentName
from app.models.organization import Organization
from app.models.project import Project
from app.repositories.environment_repository import EnvironmentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate
from app.services.environment_service import EnvironmentService
from app.services.project_service import ProjectService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    repo = OrganizationRepository(session)
    return await repo.create(name=slug.replace("-", " ").title(), slug=slug)


async def _make_project(
    session: AsyncSession,
    org: Organization,
    slug: str = "demo",
    name: str = "Demo Project",
) -> Project:
    svc = ProjectService(session)
    return await svc.create_project(
        ProjectCreate(
            organization_id=org.id,
            name=name,
            slug=slug,
            description="Test project",
        )
    )


# ---------------------------------------------------------------------------
# Auto-environment creation
# ---------------------------------------------------------------------------


async def test_create_project_auto_creates_three_environments(
    db_session: AsyncSession,
) -> None:
    """Creating a project automatically generates dev, staging, and prod environments."""
    org = await _make_org(db_session, "proj-svc-auto-env-org")
    project = await _make_project(db_session, org, slug="auto-env-project")

    env_names = {e.name for e in project.environments}

    assert len(project.environments) == 3
    assert EnvironmentName.DEV in env_names
    assert EnvironmentName.STAGING in env_names
    assert EnvironmentName.PROD in env_names


async def test_create_project_dev_is_default_environment(db_session: AsyncSession) -> None:
    """The dev environment is marked as the default after project creation."""
    org = await _make_org(db_session, "proj-svc-default-env-org")
    project = await _make_project(db_session, org, slug="default-env-project")

    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)
    non_dev_envs = [e for e in project.environments if e.name != EnvironmentName.DEV]

    assert dev_env.is_default is True
    for env in non_dev_envs:
        assert env.is_default is False


async def test_create_project_only_one_default_environment(db_session: AsyncSession) -> None:
    """Exactly one environment carries is_default=True after project creation."""
    org = await _make_org(db_session, "proj-svc-one-default-org")
    project = await _make_project(db_session, org, slug="one-default-project")

    defaults = [e for e in project.environments if e.is_default]

    assert len(defaults) == 1


# ---------------------------------------------------------------------------
# Duplicate slug within the same org
# ---------------------------------------------------------------------------


async def test_create_project_duplicate_slug_raises_conflict(
    db_session: AsyncSession,
) -> None:
    """Creating a second project with the same slug in the same org raises ConflictError."""
    org = await _make_org(db_session, "proj-svc-dup-slug-org")
    await _make_project(db_session, org, slug="dup-slug")

    svc = ProjectService(db_session)
    with pytest.raises(ConflictError, match="already exists"):
        await svc.create_project(
            ProjectCreate(
                organization_id=org.id,
                name="Another Project",
                slug="dup-slug",
            )
        )


async def test_same_slug_different_org_is_allowed(db_session: AsyncSession) -> None:
    """The same project slug is permitted across different organizations."""
    org_a = await _make_org(db_session, "proj-svc-same-slug-org-a")
    org_b = await _make_org(db_session, "proj-svc-same-slug-org-b")

    project_a = await _make_project(db_session, org_a, slug="shared-slug")
    project_b = await _make_project(db_session, org_b, slug="shared-slug")

    assert project_a.id != project_b.id
    assert project_a.slug == project_b.slug


# ---------------------------------------------------------------------------
# Default environment cannot be deleted
# ---------------------------------------------------------------------------


async def test_delete_default_environment_raises_validation_error(
    db_session: AsyncSession,
) -> None:
    """EnvironmentService.delete_environment() raises ValidationError for the default env."""
    org = await _make_org(db_session, "proj-svc-del-default-env-org")
    project = await _make_project(db_session, org, slug="del-default-env-project")

    env_svc = EnvironmentService(db_session)
    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)

    with pytest.raises(ValidationError, match="Cannot delete the default environment"):
        await env_svc.delete_environment(dev_env.id)


async def test_delete_non_default_environment_succeeds(db_session: AsyncSession) -> None:
    """Non-default environments can be deleted without error."""
    org = await _make_org(db_session, "proj-svc-del-non-default-org")
    project = await _make_project(db_session, org, slug="del-non-default-project")

    env_repo = EnvironmentRepository(db_session)
    env_svc = EnvironmentService(db_session)

    staging_env = next(
        e for e in project.environments if e.name == EnvironmentName.STAGING
    )

    # Should not raise
    await env_svc.delete_environment(staging_env.id)

    # Verify it's gone
    remaining = await env_repo.get_by_name(project.id, EnvironmentName.STAGING)
    assert remaining is None


# ---------------------------------------------------------------------------
# get_project / get_project_by_slug
# ---------------------------------------------------------------------------


async def test_get_project_by_slug_returns_project(db_session: AsyncSession) -> None:
    """get_project_by_slug() retrieves the correct project for the given org+slug."""
    org = await _make_org(db_session, "proj-svc-by-slug-org")
    created = await _make_project(db_session, org, slug="by-slug-proj")

    svc = ProjectService(db_session)
    found = await svc.get_project_by_slug(org.id, "by-slug-proj")

    assert found.id == created.id


async def test_get_project_loads_environments_eagerly(db_session: AsyncSession) -> None:
    """get_project() returns a project with environments already loaded."""
    org = await _make_org(db_session, "proj-svc-eager-env-org")
    created = await _make_project(db_session, org, slug="eager-env-proj")

    svc = ProjectService(db_session)
    fetched = await svc.get_project(created.id)

    assert len(fetched.environments) == 3
