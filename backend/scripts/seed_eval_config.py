"""Idempotent seed script — creates the default EvalConfig for the demo project.

Requires the demo org + project to already exist (run seed_data.py first).

Usage (from backend/ directory or container /app):
    python -m scripts.seed_eval_config
or from repository root:
    python scripts/seed_eval_config.py

The script is safe to re-run: it skips creation when the config already exists.
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

from app.db.session import async_session_factory
from app.models.eval_config import EvalConfig
from app.models.organization import Organization
from app.models.project import Project


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORG_SLUG = "acme"
PROJECT_SLUG = "demo"
CONFIG_NAME = "default"

DEFAULT_EVALUATORS: list[dict] = [
    {"name": "exact_match", "weight": 1.0},
    {"name": "contains", "weight": 0.5},
    {"name": "length_bounds", "weight": 0.5},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def _err(msg: str) -> None:
    print(f"  [err]  {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main seed coroutine
# ---------------------------------------------------------------------------


async def seed(session_factory=None) -> None:
    factory = session_factory or async_session_factory

    async with factory() as session:
        # ------------------------------------------------------------------
        # 1. Resolve organization
        # ------------------------------------------------------------------
        print(f"\n==> Resolving organization '{ORG_SLUG}'")
        org_result = await session.execute(
            select(Organization).where(Organization.slug == ORG_SLUG)
        )
        org: Organization | None = org_result.scalars().first()
        if org is None:
            _err(
                f"Organization '{ORG_SLUG}' not found. "
                "Run 'python -m scripts.seed_data' first."
            )
            sys.exit(1)
        _ok(f"Found organization '{org.slug}' (id={org.id})")

        # ------------------------------------------------------------------
        # 2. Resolve project
        # ------------------------------------------------------------------
        print(f"\n==> Resolving project '{PROJECT_SLUG}'")
        project_result = await session.execute(
            select(Project).where(
                Project.organization_id == org.id,
                Project.slug == PROJECT_SLUG,
            )
        )
        project: Project | None = project_result.scalars().first()
        if project is None:
            _err(
                f"Project '{PROJECT_SLUG}' not found under org '{ORG_SLUG}'. "
                "Run 'python -m scripts.seed_data' first."
            )
            sys.exit(1)
        _ok(f"Found project '{project.slug}' (id={project.id})")

        # ------------------------------------------------------------------
        # 3. Idempotency check — skip if config already exists
        # ------------------------------------------------------------------
        print(f"\n==> EvalConfig '{CONFIG_NAME}'")
        existing_result = await session.execute(
            select(EvalConfig).where(
                EvalConfig.org_id == org.id,
                EvalConfig.project_id == project.id,
                EvalConfig.name == CONFIG_NAME,
            )
        )
        existing: EvalConfig | None = existing_result.scalars().first()
        if existing is not None:
            _skip(
                f"EvalConfig '{CONFIG_NAME}' already exists for project "
                f"'{PROJECT_SLUG}' (id={existing.id})"
            )
            print("\nSeed complete (no changes made).\n")
            return

        # ------------------------------------------------------------------
        # 4. Create the default config
        # ------------------------------------------------------------------
        config = EvalConfig(
            org_id=org.id,
            project_id=project.id,
            name=CONFIG_NAME,
            evaluators=DEFAULT_EVALUATORS,
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)

        _ok(
            f"Created EvalConfig '{CONFIG_NAME}' "
            f"(id={config.id}, project='{PROJECT_SLUG}')"
        )
        print(f"\n  Evaluators stored:")
        for ev in config.evaluators:
            params_note = f", params={ev['params']}" if "params" in ev else ""
            print(f"    - {ev['name']} (weight={ev['weight']}{params_note})")

    print("\nSeed complete.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(seed())
