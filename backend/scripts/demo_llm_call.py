"""
demo_llm_call.py — Phase 3 "first real call" demo script.

Usage (from backend/ directory):
    python -m scripts.demo_llm_call
    python -m scripts.demo_llm_call "Explain async/await in one sentence."

What it does:
1. Loads .env from backend/.env (via pydantic-settings / dotenv).
2. Connects to the database and looks up the seeded demo org / project /
   environment / API key created by scripts/seed_data.py.
3. If none exist it creates a minimal demo org on the fly.
4. Calls llm_service.run_and_log() with feature="demo".
5. Prints the LLM output, token counts, latency, and the new trace ID.

Exceptions are intentionally NOT swallowed:
- Missing OPENAI_API_KEY → raises immediately with a clear message.
- OpenAI network errors → propagate so the caller sees the real error.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure backend/ is on sys.path when the script is run directly.
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# ---------------------------------------------------------------------------
# Imports — after sys.path is fixed.
# ---------------------------------------------------------------------------
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.api_key import APIKey
from app.models.enums import EnvironmentName, UserRole
from app.models.environment import Environment
from app.models.organization import Organization
from app.models.project import Project
from app.services.llm_service import run_and_log

# ---------------------------------------------------------------------------
# Seed constants — must match scripts/seed_data.py
# ---------------------------------------------------------------------------
_DEMO_ORG_SLUG = "acme"
_DEMO_PROJECT_SLUG = "demo"
_DEMO_API_KEY_NAME = "default-dev"
_DEMO_ENV = EnvironmentName.DEV

_FALLBACK_ORG_NAME = "Demo Org (auto)"
_FALLBACK_ORG_SLUG = "demo-auto"
_FALLBACK_PROJECT_NAME = "Demo Project (auto)"
_FALLBACK_PROJECT_SLUG = "demo-auto-proj"
_FALLBACK_KEY_NAME = "demo-auto-key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_api_key() -> None:
    """Abort immediately if OPENAI_API_KEY is missing or empty."""
    if not settings.OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set.\n"
            "Add it to backend/.env:  OPENAI_API_KEY=sk-...\n"
            "then re-run this script."
        )


async def _resolve_demo_context(
    db: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Return (org_id, project_id, env_id, api_key_id) for the demo dataset.

    Looks up the rows created by seed_data.py.  If they are absent (e.g. fresh
    database with no seed run), creates minimal stand-in rows so the demo still
    works without requiring a full seed.
    """
    # --- Try to find the seeded org ---
    org_row = await db.execute(
        select(Organization).where(Organization.slug == _DEMO_ORG_SLUG)
    )
    org: Organization | None = org_row.scalars().first()

    if org is None:
        # Fallback: check the auto-created slug
        org_row = await db.execute(
            select(Organization).where(Organization.slug == _FALLBACK_ORG_SLUG)
        )
        org = org_row.scalars().first()

    if org is None:
        print(
            "[demo] Seeded org not found — creating a minimal demo org. "
            "Run `python -m scripts.seed_data` for the full dataset."
        )
        org = Organization(
            name=_FALLBACK_ORG_NAME,
            slug=_FALLBACK_ORG_SLUG,
        )
        db.add(org)
        await db.flush()

    # --- Resolve project ---
    proj_row = await db.execute(
        select(Project).where(
            Project.organization_id == org.id,
            Project.slug.in_([_DEMO_PROJECT_SLUG, _FALLBACK_PROJECT_SLUG]),
        )
    )
    project: Project | None = proj_row.scalars().first()

    if project is None:
        project = Project(
            organization_id=org.id,
            name=_FALLBACK_PROJECT_NAME,
            slug=_FALLBACK_PROJECT_SLUG,
        )
        db.add(project)
        await db.flush()

    # --- Resolve environment ---
    env_row = await db.execute(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.name == _DEMO_ENV,
        )
    )
    env: Environment | None = env_row.scalars().first()

    if env is None:
        env = Environment(
            project_id=project.id,
            name=_DEMO_ENV,
        )
        db.add(env)
        await db.flush()

    # --- Resolve API key ---
    key_row = await db.execute(
        select(APIKey).where(
            APIKey.project_id == project.id,
            APIKey.environment_id == env.id,
        )
    )
    api_key: APIKey | None = key_row.scalars().first()

    if api_key is None:
        # Create a placeholder key row (hashed_key / key_prefix are not used
        # by run_and_log — it only needs the UUID as a foreign key reference).
        api_key = APIKey(
            project_id=project.id,
            environment_id=env.id,
            name=_FALLBACK_KEY_NAME,
            key_prefix="demo0000",
            hashed_key="__demo__",
            is_active=True,
        )
        db.add(api_key)
        await db.flush()

    return org.id, project.id, env.id, api_key.id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    _check_api_key()

    prompt = sys.argv[1] if len(sys.argv) > 1 else "Say hello in one sentence."

    print(f"\n{'=' * 60}")
    print(f"  Prism — Phase 3 LLM Demo")
    print(f"{'=' * 60}")
    print(f"  Prompt : {prompt}")
    print(f"  Model  : {settings.LLM_DEFAULT_MODEL} (default)")
    print(f"{'=' * 60}\n")

    async with async_session_factory() as db:
        org_id, project_id, env_id, api_key_id = await _resolve_demo_context(db)

        print("[demo] Calling LLM via run_and_log()…\n")

        resp = await run_and_log(
            db,
            org_id=org_id,
            project_id=project_id,
            env_id=env_id,
            api_key_id=api_key_id,
            feature="demo",
            prompt=prompt,
        )

        # Fetch the trace we just wrote to get its UUID
        from app.models.trace import Trace
        trace_row = await db.execute(
            select(Trace)
            .where(Trace.project_id == project_id)
            .order_by(Trace.created_at.desc())
            .limit(1)
        )
        trace = trace_row.scalars().first()

        await db.commit()

    print(f"Output\n------\n{resp.output}\n")
    print(f"{'─' * 60}")
    print(f"  model             : {resp.model}")
    print(f"  prompt_tokens     : {resp.prompt_tokens}")
    print(f"  completion_tokens : {resp.completion_tokens}")
    print(f"  total_tokens      : {resp.total_tokens}")
    print(f"  latency_ms        : {resp.latency_ms} ms")
    if trace:
        print(f"  trace_id          : {trace.id}")
    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
