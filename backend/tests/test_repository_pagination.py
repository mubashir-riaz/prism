"""Tests for repository pagination: offset/limit and count correctness."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.models.enums import UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_orgs(session: AsyncSession, n: int, prefix: str) -> list[Organization]:
    """Create `n` organizations with slugs '{prefix}-0' … '{prefix}-{n-1}'."""
    repo = OrganizationRepository(session)
    return [
        await repo.create(name=f"{prefix} {i}", slug=f"{prefix}-{i}")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# list() — offset and limit
# ---------------------------------------------------------------------------


async def test_list_with_limit_returns_at_most_limit_items(
    db_session: AsyncSession,
) -> None:
    """list(limit=3) returns at most 3 items regardless of total count."""
    await _make_orgs(db_session, 5, "pag-limit")
    repo = OrganizationRepository(db_session)

    items, _ = await repo.list(limit=3)

    assert len(items) <= 3


async def test_list_with_offset_skips_first_n_items(db_session: AsyncSession) -> None:
    """list(offset=2) skips the first 2 records from the full result set."""
    await _make_orgs(db_session, 5, "pag-offset")
    repo = OrganizationRepository(db_session)

    all_items, total = await repo.list(limit=100)
    offset_items, offset_total = await repo.list(offset=2, limit=100)

    # The offset query reports the same total count
    assert offset_total == total
    # But fewer items are returned
    assert len(offset_items) == len(all_items) - 2


async def test_list_offset_beyond_total_returns_empty(db_session: AsyncSession) -> None:
    """list(offset=N) where N >= total returns an empty item list."""
    await _make_orgs(db_session, 3, "pag-beyond")
    repo = OrganizationRepository(db_session)

    _, total = await repo.list(limit=100)
    items, total2 = await repo.list(offset=total + 100, limit=100)

    assert total2 == total  # total count unchanged
    assert len(items) == 0


async def test_list_limit_zero_returns_empty_items(db_session: AsyncSession) -> None:
    """list(limit=0) returns no items but the correct total count."""
    await _make_orgs(db_session, 2, "pag-zero-limit")
    repo = OrganizationRepository(db_session)

    _, total_all = await repo.list(limit=100)
    items, total = await repo.list(limit=0)

    assert total == total_all
    assert len(items) == 0


# ---------------------------------------------------------------------------
# count() correctness
# ---------------------------------------------------------------------------


async def test_count_matches_list_total(db_session: AsyncSession) -> None:
    """count() returns the same value as the total from list()."""
    await _make_orgs(db_session, 4, "pag-count")
    repo = OrganizationRepository(db_session)

    count = await repo.count()
    _, total = await repo.list(limit=1000)

    assert count == total


async def test_count_with_filter_matches_filtered_list_total(
    db_session: AsyncSession,
) -> None:
    """count(filters=...) is consistent with list(filters=...)."""
    repo = OrganizationRepository(db_session)

    await repo.create(name="Active One", slug="pag-cnt-active-1", is_active=True)
    await repo.create(name="Active Two", slug="pag-cnt-active-2", is_active=True)
    await repo.create(name="Inactive One", slug="pag-cnt-inactive-1", is_active=False)

    active_count = await repo.count(filters={"is_active": True})
    _, active_list_total = await repo.list(filters={"is_active": True}, limit=1000)

    assert active_count == active_list_total


# ---------------------------------------------------------------------------
# Pagination window consistency
# ---------------------------------------------------------------------------


async def test_paginated_windows_cover_all_records(db_session: AsyncSession) -> None:
    """Stepping through pages with page_size=2 covers every created record."""
    created = await _make_orgs(db_session, 6, "pag-window")
    created_ids = {o.id for o in created}

    repo = OrganizationRepository(db_session)
    _, total = await repo.list(limit=1000)

    page_size = 2
    collected_ids: set = set()

    for page in range((total + page_size - 1) // page_size):
        items, _ = await repo.list(offset=page * page_size, limit=page_size)
        for item in items:
            collected_ids.add(item.id)

    # Every org we created must appear in the collected pages
    assert created_ids.issubset(collected_ids)


# ---------------------------------------------------------------------------
# User repository pagination (multi-table sanity check)
# ---------------------------------------------------------------------------


async def test_user_list_by_org_pagination(db_session: AsyncSession) -> None:
    """list_by_org() pagination works correctly for UserRepository."""
    org_repo = OrganizationRepository(db_session)
    org = await org_repo.create(name="Pag User Org", slug="pag-user-org")

    user_repo = UserRepository(db_session)
    for i in range(5):
        await user_repo.create(
            organization_id=org.id,
            email=f"pag-user-{i}@example.com",
            role=UserRole.MEMBER,
            hashed_password="",
        )

    first_page, total = await user_repo.list_by_org(org.id, offset=0, limit=3)
    second_page, total2 = await user_repo.list_by_org(org.id, offset=3, limit=3)

    assert total == 5
    assert total2 == 5
    assert len(first_page) == 3
    assert len(second_page) == 2

    first_ids = {u.id for u in first_page}
    second_ids = {u.id for u in second_page}
    assert first_ids.isdisjoint(second_ids)
