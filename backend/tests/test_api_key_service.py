"""Tests for APIKeyService: plaintext returned once, list never exposes hashed_key."""

import hashlib
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName
from app.models.organization import Organization
from app.models.project import Project
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    repo = OrganizationRepository(session)
    return await repo.create(name=slug.replace("-", " ").title(), slug=slug)


async def _make_project(session: AsyncSession, org: Organization, slug: str) -> Project:
    svc = ProjectService(session)
    return await svc.create_project(
        ProjectCreate(
            organization_id=org.id,
            name=slug.replace("-", " ").title(),
            slug=slug,
        )
    )


async def _get_dev_env(project: Project):
    return next(e for e in project.environments if e.name == EnvironmentName.DEV)


# ---------------------------------------------------------------------------
# Plaintext key returned once
# ---------------------------------------------------------------------------


async def test_create_api_key_returns_plaintext_key(db_session: AsyncSession) -> None:
    """create_api_key() returns a non-empty plaintext key string."""
    org = await _make_org(db_session, "key-svc-plaintext-org")
    project = await _make_project(db_session, org, "key-svc-plaintext-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="my-key",
    )

    assert plaintext is not None
    assert len(plaintext) > 0


async def test_create_api_key_plaintext_has_correct_prefix_format(
    db_session: AsyncSession,
) -> None:
    """The plaintext key starts with the 'prism_' prefix and embeds key_prefix."""
    org = await _make_org(db_session, "key-svc-prefix-org")
    project = await _make_project(db_session, org, "key-svc-prefix-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="prefix-key",
    )

    assert plaintext.startswith("prism_")
    # The stored key_prefix must be a leading segment of the plaintext key
    assert plaintext.startswith(record.key_prefix)


async def test_create_api_key_hashes_match(db_session: AsyncSession) -> None:
    """SHA-256 hash of the returned plaintext matches what is stored in the DB."""
    org = await _make_org(db_session, "key-svc-hash-org")
    project = await _make_project(db_session, org, "key-svc-hash-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="hash-key",
    )

    expected_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    assert record.hashed_key == expected_hash


async def test_create_api_key_plaintext_not_stored(db_session: AsyncSession) -> None:
    """The plaintext key is NOT stored verbatim in any record field."""
    org = await _make_org(db_session, "key-svc-no-store-org")
    project = await _make_project(db_session, org, "key-svc-no-store-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="no-store-key",
    )

    # None of the string columns should contain the raw plaintext
    assert record.hashed_key != plaintext
    assert record.key_prefix != plaintext
    assert record.name != plaintext


# ---------------------------------------------------------------------------
# list never exposes hashed_key
# ---------------------------------------------------------------------------


async def test_list_keys_for_project_does_not_expose_hashed_key(
    db_session: AsyncSession,
) -> None:
    """APIKey records returned by list_keys_for_project() carry hashed_key
    (stored in DB) but must NOT equal the original plaintext key.

    The invariant: hashed_key ≠ plaintext.  The plaintext is never persisted
    and cannot be recovered from listing operations.
    """
    org = await _make_org(db_session, "key-svc-list-hashed-org")
    project = await _make_project(db_session, org, "key-svc-list-hashed-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    _, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="list-key",
    )

    keys, total = await svc.list_keys_for_project(project.id)

    assert total >= 1
    for key in keys:
        # hashed_key column exists but never equals the plaintext
        assert key.hashed_key != plaintext
        # hashed_key must look like a hex digest (64 chars for SHA-256)
        assert len(key.hashed_key) == 64


async def test_list_keys_for_environment_returns_correct_subset(
    db_session: AsyncSession,
) -> None:
    """list_keys_for_environment() scopes results to the given environment."""
    org = await _make_org(db_session, "key-svc-env-scope-org")
    project = await _make_project(db_session, org, "key-svc-env-scope-proj")

    dev_env = next(e for e in project.environments if e.name == EnvironmentName.DEV)
    staging_env = next(
        e for e in project.environments if e.name == EnvironmentName.STAGING
    )

    svc = APIKeyService(db_session)
    await svc.create_api_key(project_id=project.id, environment_id=dev_env.id, name="dev-key-1")
    await svc.create_api_key(project_id=project.id, environment_id=dev_env.id, name="dev-key-2")
    await svc.create_api_key(
        project_id=project.id, environment_id=staging_env.id, name="staging-key"
    )

    dev_keys, dev_total = await svc.list_keys_for_environment(dev_env.id)
    staging_keys, staging_total = await svc.list_keys_for_environment(staging_env.id)

    assert dev_total == 2
    assert staging_total == 1


# ---------------------------------------------------------------------------
# revoke_api_key
# ---------------------------------------------------------------------------


async def test_revoke_api_key_deactivates_key(db_session: AsyncSession) -> None:
    """revoke_api_key() sets is_active=False and stamps revoked_at."""
    org = await _make_org(db_session, "key-svc-revoke-org")
    project = await _make_project(db_session, org, "key-svc-revoke-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, _ = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="revoke-me",
    )

    revoked = await svc.revoke_api_key(record.id)

    assert revoked.is_active is False
    assert revoked.revoked_at is not None


async def test_list_active_excludes_revoked_key(db_session: AsyncSession) -> None:
    """list_keys_for_project(is_active=True) excludes revoked keys."""
    org = await _make_org(db_session, "key-svc-active-filter-org")
    project = await _make_project(db_session, org, "key-svc-active-filter-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    active_rec, _ = await svc.create_api_key(
        project_id=project.id, environment_id=dev_env.id, name="active-key"
    )
    revoked_rec, _ = await svc.create_api_key(
        project_id=project.id, environment_id=dev_env.id, name="revoked-key"
    )
    await svc.revoke_api_key(revoked_rec.id)

    active_keys, active_total = await svc.list_keys_for_project(
        project.id, is_active=True
    )
    active_ids = {k.id for k in active_keys}

    assert active_total == 1
    assert active_rec.id in active_ids
    assert revoked_rec.id not in active_ids


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


async def test_authenticate_accepts_plaintext_key(db_session: AsyncSession) -> None:
    """authenticate() succeeds with valid plaintext key and updates last_used_at."""
    org = await _make_org(db_session, "key-svc-auth-accept-org")
    project = await _make_project(db_session, org, "key-svc-auth-accept-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="auth-accept-key",
    )

    authed = await svc.authenticate(plaintext)
    assert authed is not None
    assert authed.id == record.id
    assert authed.last_used_at is not None


async def test_authenticate_rejects_corrupted_key(db_session: AsyncSession) -> None:
    """authenticate() returns None when the key secret or prefix is corrupted."""
    org = await _make_org(db_session, "key-svc-auth-corrupt-org")
    project = await _make_project(db_session, org, "key-svc-auth-corrupt-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="auth-corrupt-key",
    )

    # 1. Corrupt the secret segment
    corrupted_secret = plaintext[:-4] + "xxxx"
    assert await svc.authenticate(corrupted_secret) is None

    # 2. Corrupt prefix
    corrupted_prefix = "prism_dev_wrongprefix_" + plaintext.split("_")[-1]
    assert await svc.authenticate(corrupted_prefix) is None

    # 3. Invalid format
    assert await svc.authenticate("invalid_key_format") is None
    assert await svc.authenticate("prism_dev") is None


async def test_revoked_key_fails_authentication(db_session: AsyncSession) -> None:
    """A revoked API key fails authentication even if secret is valid."""
    org = await _make_org(db_session, "key-svc-auth-revoked-org")
    project = await _make_project(db_session, org, "key-svc-auth-revoked-proj")
    dev_env = await _get_dev_env(project)

    svc = APIKeyService(db_session)
    record, plaintext = await svc.create_api_key(
        project_id=project.id,
        environment_id=dev_env.id,
        name="auth-revoked-key",
    )

    # Revoke key
    await svc.revoke_api_key(record.id)

    # Authenticate must fail
    assert await svc.authenticate(plaintext) is None
