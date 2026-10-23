"""Idempotent seed script for Prism.

Creates a canonical demo dataset:
  - Org:     Acme AI  (slug: acme)
  - User:    owner@acme.test  (role: OWNER, dev password: password)
  - Project: Demo Project  (slug: demo)
  - Envs:    dev (default), staging, prod  — auto-created by ProjectService
  - API key: default-dev  (attached to the dev environment)

Re-running the script is safe: each resource is skipped when its slug or
email is already present in the database. Existing users are not re-hashed.

Usage (from backend/ directory or container /app):
    python -m scripts.seed_data
or from repository root:
    python scripts/seed_data.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Ensure the backend directory is in sys.path when running as a script
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import async_session_factory
from app.models.enums import EnvironmentName, UserRole
from app.models.organization import Organization
from app.models.user import User
from app.models.project import Project
from app.models.environment import Environment
from app.models.api_key import APIKey
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.environment_repository import EnvironmentRepository
from app.repositories.api_key_repository import APIKeyRepository
from app.services.organization_service import OrganizationService
from app.services.user_service import UserService
from app.services.project_service import ProjectService
from app.services.api_key_service import APIKeyService
from app.schemas.organization import OrganizationCreate
from app.schemas.project import ProjectCreate

# ---------------------------------------------------------------------------
# Demo data constants
# ---------------------------------------------------------------------------

ORG_NAME = "Acme AI"
ORG_SLUG = "acme"

OWNER_EMAIL = "owner@acme.test"
OWNER_ROLE = UserRole.OWNER
OWNER_FULL_NAME = "Acme Owner"
OWNER_PASSWORD = "password"  # DEV ONLY CREDENTIAL

PROJECT_NAME = "Demo Project"
PROJECT_SLUG = "demo"
PROJECT_DESCRIPTION = "Auto-seeded demo project."

API_KEY_NAME = "default-dev"
API_KEY_ENV = EnvironmentName.DEV


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def _warn(msg: str) -> None:
    print(f"  [warn] {msg}")


# ---------------------------------------------------------------------------
# Main seed coroutine
# ---------------------------------------------------------------------------


async def seed(session_factory=None) -> None:
    factory = session_factory or async_session_factory
    plaintext_key: str | None = None

    async with factory() as session:
        # ------------------------------------------------------------------
        # 1. Organization
        # ------------------------------------------------------------------
        print("\n==> Organization")
        org_repo = OrganizationRepository(session)
        org_svc = OrganizationService(org_repo)

        org: Organization | None = await org_repo.get_by_slug(ORG_SLUG)
        if org is not None:
            _skip(f"Organization '{ORG_SLUG}' already exists (id={org.id})")
        else:
            org = await org_svc.create_organization(
                OrganizationCreate(name=ORG_NAME, slug=ORG_SLUG)
            )
            _ok(f"Created organization '{org.slug}' (id={org.id})")

        # ------------------------------------------------------------------
        # 2. Owner user
        # ------------------------------------------------------------------
        print("\n==> Owner user")
        user_repo = UserRepository(session)
        user_svc = UserService(user_repo)

        user: User | None = await user_repo.get_by_email(OWNER_EMAIL)
        if user is not None:
            _skip(f"User '{OWNER_EMAIL}' already exists (id={user.id})")
        else:
            _warn("DEV-ONLY CREDENTIAL: Seeding demo owner with password 'password'.")
            _warn("DO NOT USE THIS CREDENTIAL IN PRODUCTION ENVIRONMENTS!")
            hashed_pw = hash_password(OWNER_PASSWORD)
            user = await user_svc.create_user(
                org_id=org.id,
                email=OWNER_EMAIL,
                role=OWNER_ROLE,
                full_name=OWNER_FULL_NAME,
                hashed_password=hashed_pw,
            )
            _ok(f"Created user '{user.email}' with role '{user.role}' (id={user.id})")

        # ------------------------------------------------------------------
        # 3. Project  (auto-creates 3 environments via ProjectService)
        # ------------------------------------------------------------------
        print("\n==> Project")
        project_repo = ProjectRepository(session)
        env_repo = EnvironmentRepository(session)
        project_svc = ProjectService(project_repo, env_repo)

        project: Project | None = await project_repo.get_by_slug(org.id, PROJECT_SLUG)
        if project is not None:
            _skip(f"Project '{PROJECT_SLUG}' already exists (id={project.id})")
            # Load environments in case we need them below
            project = await project_repo.get_with_environments(project.id) or project
        else:
            project = await project_svc.create_project(
                ProjectCreate(
                    organization_id=org.id,
                    name=PROJECT_NAME,
                    slug=PROJECT_SLUG,
                    description=PROJECT_DESCRIPTION,
                )
            )
            _ok(
                f"Created project '{project.slug}' with {len(project.environments)} "
                f"environments (id={project.id})"
            )

        # ------------------------------------------------------------------
        # 4. Resolve the dev environment
        # ------------------------------------------------------------------
        print("\n==> Environments")
        dev_env: Environment | None = await env_repo.get_by_name(project.id, API_KEY_ENV)
        if dev_env is None:
            # Defensive: should not happen when ProjectService created the project,
            # but guard against edge-cases where the project was seeded without envs.
            _warn(f"Dev environment not found for project '{PROJECT_SLUG}'.")
            sys.exit(1)

        _ok(
            f"Dev environment present (id={dev_env.id}, "
            f"is_default={dev_env.is_default})"
        )

        # ------------------------------------------------------------------
        # 5. API key  (idempotent: skip if a key named 'default-dev' exists
        #              on the dev environment)
        # ------------------------------------------------------------------
        print("\n==> API key")
        api_key_repo = APIKeyRepository(session)
        api_key_svc = APIKeyService(api_key_repo)

        # Check for an existing active key with this name in the dev environment
        existing_keys_stmt = select(APIKey).where(
            APIKey.environment_id == dev_env.id,
            APIKey.name == API_KEY_NAME,
            APIKey.is_active.is_(True),
        )
        result = await session.execute(existing_keys_stmt)
        existing_key: APIKey | None = result.scalars().first()

        if existing_key is not None:
            _skip(
                f"Active API key '{API_KEY_NAME}' already exists "
                f"(prefix={existing_key.key_prefix}). "
                "Plaintext cannot be recovered — create a new key if needed."
            )
        else:
            _api_key_record, plaintext_key = await api_key_svc.create_api_key(
                project_id=project.id,
                environment_id=dev_env.id,
                name=API_KEY_NAME,
            )
            _ok(
                f"Created API key '{API_KEY_NAME}' "
                f"(prefix={_api_key_record.key_prefix}, id={_api_key_record.id})"
            )

    # ------------------------------------------------------------------
    # Print summary & credentials
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  DEV CREDENTIALS & ACCESS INFO (DEV ONLY):")
    print(f"  Owner Email:    {OWNER_EMAIL}")
    print(f"  Owner Password: {OWNER_PASSWORD}")
    print("  WARNING: This is a dev-only credential. Do not use in production!")
    if plaintext_key is not None:
        print("\n  PLAINTEXT API KEY (shown once — store it securely):")
        print(f"  {plaintext_key}")
    print("=" * 60 + "\n")

    print("Seed complete.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(seed())
