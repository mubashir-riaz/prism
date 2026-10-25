"""Tests for UserService: create, duplicate-email rules, cross-org email re-use."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError
from app.models.enums import UserRole
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    repo = OrganizationRepository(session)
    return await repo.create(name=slug.replace("-", " ").title(), slug=slug)


async def _make_user(
    session: AsyncSession,
    org: Organization,
    email: str,
    role: UserRole = UserRole.MEMBER,
) -> User:
    svc = UserService(session)
    return await svc.create_user(org_id=org.id, email=email, role=role)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_user_returns_record(db_session: AsyncSession) -> None:
    """create_user() returns a persisted User with the expected attributes."""
    org = await _make_org(db_session, "user-svc-org-1")
    svc = UserService(db_session)

    user = await svc.create_user(
        org_id=org.id,
        email="alice@example.com",
        role=UserRole.OWNER,
        full_name="Alice Example",
    )

    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.role == UserRole.OWNER
    assert user.full_name == "Alice Example"
    assert user.organization_id == org.id
    assert user.is_active is True


async def test_create_user_defaults_to_member_role(db_session: AsyncSession) -> None:
    """When no role is supplied, the user defaults to MEMBER."""
    org = await _make_org(db_session, "user-svc-org-default-role")
    svc = UserService(db_session)

    user = await svc.create_user(org_id=org.id, email="bob@example.com")

    assert user.role == UserRole.MEMBER


async def test_create_user_no_full_name(db_session: AsyncSession) -> None:
    """full_name is optional and defaults to None."""
    org = await _make_org(db_session, "user-svc-org-no-name")
    svc = UserService(db_session)

    user = await svc.create_user(org_id=org.id, email="no-name@example.com")

    assert user.full_name is None


# ---------------------------------------------------------------------------
# Duplicate email — same organization
# ---------------------------------------------------------------------------


async def test_duplicate_email_same_org_raises_conflict(db_session: AsyncSession) -> None:
    """Creating a second user with the same email in the same org raises ConflictError."""
    org = await _make_org(db_session, "user-svc-dup-email-org")
    await _make_user(db_session, org, "dup@example.com")

    svc = UserService(db_session)
    with pytest.raises(ConflictError, match="already exists"):
        await svc.create_user(org_id=org.id, email="dup@example.com")


# ---------------------------------------------------------------------------
# Same email, different organization
# ---------------------------------------------------------------------------


async def test_same_email_different_org_raises_conflict(db_session: AsyncSession) -> None:
    """Email uniqueness is global (not scoped to org), so the same email in a
    different org must also raise ConflictError.

    The User model has a globally unique index on `email`.  This test confirms
    that the service correctly rejects the duplicate regardless of org affiliation.
    """
    org_a = await _make_org(db_session, "user-svc-cross-org-a")
    org_b = await _make_org(db_session, "user-svc-cross-org-b")

    await _make_user(db_session, org_a, "shared@example.com")

    svc = UserService(db_session)
    with pytest.raises(ConflictError, match="already exists"):
        await svc.create_user(org_id=org_b.id, email="shared@example.com")


# ---------------------------------------------------------------------------
# get_user_by_email
# ---------------------------------------------------------------------------


async def test_get_user_by_email_success(db_session: AsyncSession) -> None:
    """get_user_by_email() returns the correct user record."""
    org = await _make_org(db_session, "user-svc-by-email-org")
    created = await _make_user(db_session, org, "find-me@example.com")

    svc = UserService(db_session)
    found = await svc.get_user_by_email("find-me@example.com")

    assert found.id == created.id


# ---------------------------------------------------------------------------
# list_users_in_org
# ---------------------------------------------------------------------------


async def test_list_users_in_org_returns_correct_subset(db_session: AsyncSession) -> None:
    """list_users_in_org() returns only users belonging to the specified org."""
    org_a = await _make_org(db_session, "user-svc-list-org-a")
    org_b = await _make_org(db_session, "user-svc-list-org-b")

    await _make_user(db_session, org_a, "u1@example.com")
    await _make_user(db_session, org_a, "u2@example.com")
    await _make_user(db_session, org_b, "u3@example.com")

    svc = UserService(db_session)
    items_a, count_a = await svc.list_users_in_org(org_a.id)
    items_b, count_b = await svc.list_users_in_org(org_b.id)

    assert count_a == 2
    assert count_b == 1
    emails_a = {u.email for u in items_a}
    assert "u1@example.com" in emails_a
    assert "u2@example.com" in emails_a
    assert "u3@example.com" not in emails_a


# ---------------------------------------------------------------------------
# deactivate_user
# ---------------------------------------------------------------------------


async def test_deactivate_user_sets_is_active_false(db_session: AsyncSession) -> None:
    """deactivate_user() sets is_active to False."""
    org = await _make_org(db_session, "user-svc-deactivate-org")
    user = await _make_user(db_session, org, "deactivate-me@example.com")

    svc = UserService(db_session)
    deactivated = await svc.deactivate_user(user.id)

    assert deactivated.is_active is False


async def test_create_user_with_hashed_password(db_session: AsyncSession) -> None:
    """create_user() accepts and persists a custom hashed_password."""
    org = await _make_org(db_session, "user-svc-hash-org")
    svc = UserService(db_session)

    custom_hash = "$argon2id$v=19$m=65536,t=3,p=4$somecustomhash"
    user = await svc.create_user(
        org_id=org.id,
        email="hashed_user@example.com",
        role=UserRole.ADMIN,
        full_name="Hashed User",
        hashed_password=custom_hash,
    )

    assert user.hashed_password == custom_hash
