"""Unit and integration tests for the database seed script."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import verify_password
from app.models.api_key import APIKey
from app.models.enums import EnvironmentName, UserRole
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from scripts.seed_data import (
    API_KEY_NAME,
    ORG_NAME,
    ORG_SLUG,
    OWNER_EMAIL,
    OWNER_FULL_NAME,
    OWNER_PASSWORD,
    OWNER_ROLE,
    PROJECT_NAME,
    PROJECT_SLUG,
    seed,
)


@pytest.mark.asyncio
async def test_seed_creates_demo_data_with_hashed_password(
    db_session: AsyncSession,
) -> None:
    """seed() creates canonical org, owner user with hashed password, project, and API key."""
    # Build a sessionmaker factory from the current test session
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )

    out = io.StringIO()
    with redirect_stdout(out):
        await seed(session_factory=session_factory)
    output = out.getvalue()

    # Verify output contains dev credential warning and success messages
    assert "DEV-ONLY CREDENTIAL" in output
    assert "password" in output
    assert "Seed complete." in output

    # 1. Organization
    org_res = await db_session.execute(
        select(Organization).where(Organization.slug == ORG_SLUG)
    )
    org = org_res.scalars().first()
    assert org is not None
    assert org.name == ORG_NAME

    # 2. Owner User
    user_res = await db_session.execute(
        select(User).where(User.email == OWNER_EMAIL)
    )
    user = user_res.scalars().first()
    assert user is not None
    assert user.role == OWNER_ROLE
    assert user.full_name == OWNER_FULL_NAME
    assert user.organization_id == org.id
    assert user.is_active is True
    # Password must be hashed and verifiable with OWNER_PASSWORD
    assert user.hashed_password != ""
    assert user.hashed_password != OWNER_PASSWORD
    assert verify_password(OWNER_PASSWORD, user.hashed_password) is True

    # 3. Project & Environments
    proj_res = await db_session.execute(
        select(Project).where(Project.slug == PROJECT_SLUG)
    )
    project = proj_res.scalars().first()
    assert project is not None
    assert project.name == PROJECT_NAME
    assert project.organization_id == org.id

    # 4. API Key
    key_res = await db_session.execute(
        select(APIKey).where(APIKey.name == API_KEY_NAME)
    )
    api_key = key_res.scalars().first()
    assert api_key is not None
    assert api_key.project_id == project.id
    assert api_key.is_active is True


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_does_not_rehash_user(
    db_session: AsyncSession,
) -> None:
    """Re-running seed() is safe: does not duplicate records or re-hash the user password."""
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )

    # First run
    with redirect_stdout(io.StringIO()):
        await seed(session_factory=session_factory)

    # Fetch user after first run
    user_res = await db_session.execute(
        select(User).where(User.email == OWNER_EMAIL)
    )
    user_first = user_res.scalars().first()
    assert user_first is not None
    original_hash = user_first.hashed_password
    original_id = user_first.id

    # Second run
    out = io.StringIO()
    with redirect_stdout(out):
        await seed(session_factory=session_factory)
    output = out.getvalue()

    # Second run should skip already existing entities
    assert f"[skip] Organization '{ORG_SLUG}' already exists" in output
    assert f"[skip] User '{OWNER_EMAIL}' already exists" in output
    assert f"[skip] Project '{PROJECT_SLUG}' already exists" in output
    assert f"[skip] Active API key '{API_KEY_NAME}' already exists" in output

    # Ensure user record was NOT re-hashed or recreated
    user_res_2 = await db_session.execute(
        select(User).where(User.email == OWNER_EMAIL)
    )
    user_second = user_res_2.scalars().first()
    assert user_second is not None
    assert user_second.id == original_id
    assert user_second.hashed_password == original_hash


def test_root_scripts_wrapper_imports_and_exports_seed() -> None:
    """The root wrapper at scripts/seed_data.py properly wraps backend seed()."""
    import importlib.util
    from pathlib import Path

    root_script = Path(__file__).resolve().parent.parent.parent / "scripts" / "seed_data.py"
    assert root_script.exists()

    spec = importlib.util.spec_from_file_location("scripts.seed_data", root_script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "seed")
    assert callable(mod.seed)
    assert mod.seed.__name__ == "seed"
