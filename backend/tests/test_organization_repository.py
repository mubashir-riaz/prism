"""Tests for OrganizationRepository: create, get_by_slug, list, count."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.organization_repository import OrganizationRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(
    session: AsyncSession,
    *,
    name: str = "Test Org",
    slug: str = "test-org",
) -> Organization:
    """Create and flush a bare Organization for use in tests."""
    repo = OrganizationRepository(session)
    return await repo.create(name=name, slug=slug)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_organization_returns_record(db_session: AsyncSession) -> None:
    """create() returns a persisted Organization with the expected fields."""
    org = await _make_org(db_session, name="Acme", slug="acme")

    assert org.id is not None
    assert org.name == "Acme"
    assert org.slug == "acme"
    assert org.is_active is True
    assert org.created_at is not None
    assert org.updated_at is not None


async def test_create_organization_unique_id(db_session: AsyncSession) -> None:
    """Two organizations receive different UUIDs."""
    org_a = await _make_org(db_session, name="Org A", slug="org-a")
    org_b = await _make_org(db_session, name="Org B", slug="org-b")

    assert org_a.id != org_b.id


# ---------------------------------------------------------------------------
# get / get_by_slug
# ---------------------------------------------------------------------------


async def test_get_by_slug_returns_org(db_session: AsyncSession) -> None:
    """get_by_slug() finds the organization when the slug exists."""
    created = await _make_org(db_session, slug="find-me")
    repo = OrganizationRepository(db_session)

    found = await repo.get_by_slug("find-me")

    assert found is not None
    assert found.id == created.id
    assert found.slug == "find-me"


async def test_get_by_slug_returns_none_when_missing(db_session: AsyncSession) -> None:
    """get_by_slug() returns None for an unknown slug."""
    repo = OrganizationRepository(db_session)

    result = await repo.get_by_slug("does-not-exist-xyz")

    assert result is None


async def test_get_by_id_returns_org(db_session: AsyncSession) -> None:
    """get() returns the correct org by UUID primary key."""
    created = await _make_org(db_session, slug="by-id-org")
    repo = OrganizationRepository(db_session)

    fetched = await repo.get(created.id)

    assert fetched.id == created.id
    assert fetched.slug == "by-id-org"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list_returns_all_created_orgs(db_session: AsyncSession) -> None:
    """list() returns every organization that was created in this transaction."""
    repo = OrganizationRepository(db_session)

    # Record the baseline count before creating anything.
    _, baseline = await repo.list()

    await _make_org(db_session, slug="list-org-1")
    await _make_org(db_session, slug="list-org-2")
    await _make_org(db_session, slug="list-org-3")

    items, total = await repo.list()

    assert total == baseline + 3
    assert len(items) >= 3


async def test_list_active_excludes_inactive(db_session: AsyncSession) -> None:
    """list_active() omits organizations with is_active=False."""
    repo = OrganizationRepository(db_session)

    active = await repo.create(name="Active Org", slug="active-list-org")
    inactive = await repo.create(name="Inactive Org", slug="inactive-list-org", is_active=False)

    active_items, _ = await repo.list_active()
    active_ids = {o.id for o in active_items}

    assert active.id in active_ids
    assert inactive.id not in active_ids


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------


async def test_count_increases_after_create(db_session: AsyncSession) -> None:
    """count() reflects each new organization."""
    repo = OrganizationRepository(db_session)
    before = await repo.count()

    await _make_org(db_session, slug="count-org-1")
    await _make_org(db_session, slug="count-org-2")

    after = await repo.count()

    assert after == before + 2


async def test_count_with_filter(db_session: AsyncSession) -> None:
    """count() supports equality filters."""
    repo = OrganizationRepository(db_session)

    await repo.create(name="Active1", slug="cnt-active-1", is_active=True)
    await repo.create(name="Active2", slug="cnt-active-2", is_active=True)
    await repo.create(name="Inactive1", slug="cnt-inactive-1", is_active=False)

    active_count = await repo.count(filters={"is_active": True})
    inactive_count = await repo.count(filters={"is_active": False})

    # At minimum our two active orgs must be counted
    assert active_count >= 2
    assert inactive_count >= 1
