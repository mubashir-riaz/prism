"""Idempotent seed script for Prism.

Creates a canonical demo dataset:
  - Org:     Acme AI  (slug: acme)
  - User:    owner@acme.test  (role: OWNER, dev password: password)
  - Project: Demo Project  (slug: demo)
  - Envs:    dev (default), staging, prod  — auto-created by ProjectService
  - API key: default-dev  (attached to the dev environment)
  - Traces:  5 sample LLM traces for realistic dev/Phase 5–9 data

Re-running the script is safe: each resource is skipped when its slug or
email is already present in the database. Existing users are not re-hashed.
Traces are only seeded when none exist for the demo project.

Usage (from backend/ directory or container /app):
    python -m scripts.seed_data
or from repository root:
    python scripts/seed_data.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Ensure the backend directory is in sys.path when running as a script
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import async_session_factory
from app.models.enums import EnvironmentName, UserRole
from app.models.organization import Organization
from app.models.user import User
from app.models.project import Project
from app.models.environment import Environment
from app.models.api_key import APIKey
from app.models.trace import Trace
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.environment_repository import EnvironmentRepository
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.trace_repository import TraceRepository
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
# Sample trace data — realistic prompts/completions for Phase 5–9 dev
# ---------------------------------------------------------------------------

_SAMPLE_TRACES = [
    {
        "feature": "chat",
        "model": "gpt-4o",
        "prompt": (
            "You are a helpful assistant. The user asks:\n\n"
            "Can you explain the difference between supervised and unsupervised "
            "machine learning, and give a concrete example of each?"
        ),
        "completion": (
            "Supervised learning trains a model on labelled examples — pairs of "
            "input and desired output — so it can predict labels for new inputs. "
            "A classic example is email spam classification: you provide thousands "
            "of emails tagged 'spam' or 'not spam', and the model learns the "
            "boundary between them.\n\n"
            "Unsupervised learning, by contrast, finds structure in data without "
            "any labels. A common example is customer segmentation: given purchase "
            "history and demographics, a clustering algorithm groups customers into "
            "cohorts (e.g. 'high-value', 'budget-conscious', 'occasional buyer') "
            "without being told in advance what those groups should look like."
        ),
        "prompt_tokens": 58,
        "completion_tokens": 120,
        "latency_ms": 820,
    },
    {
        "feature": "summarize",
        "model": "gpt-4o",
        "prompt": (
            "Summarize the following research abstract in two sentences for a "
            "non-technical audience:\n\n"
            "We present a novel approach to neural architecture search (NAS) that "
            "reduces the search cost from thousands of GPU-hours to under four by "
            "combining weight sharing across candidate architectures with a "
            "differentiable relaxation of the discrete search space. Our method "
            "achieves state-of-the-art accuracy on CIFAR-10 and ImageNet while "
            "requiring 3× fewer parameters than the previous best hand-crafted "
            "architecture."
        ),
        "completion": (
            "Researchers developed a faster way to automatically design neural "
            "networks, cutting the usual weeks of computer time down to just hours. "
            "The resulting networks are more accurate and smaller than those created "
            "by hand."
        ),
        "prompt_tokens": 112,
        "completion_tokens": 42,
        "latency_ms": 390,
    },
    {
        "feature": "classify",
        "model": "claude-3-5-sonnet",
        "prompt": (
            "Classify the sentiment of the following customer review as POSITIVE, "
            "NEGATIVE, or NEUTRAL, and provide a one-sentence explanation.\n\n"
            "Review: \"The delivery took three weeks and the box arrived dented, "
            "but the product itself works exactly as advertised and I use it every "
            "day. Support answered my query within an hour.\""
        ),
        "completion": (
            "NEUTRAL — While the customer experienced shipping and packaging issues, "
            "their satisfaction with the product's functionality and responsive "
            "support balances out the negative aspects, resulting in a mixed overall "
            "impression."
        ),
        "prompt_tokens": 87,
        "completion_tokens": 45,
        "latency_ms": 470,
    },
    {
        "feature": "chat",
        "model": "claude-3-5-sonnet",
        "prompt": (
            "You are a senior software engineer reviewing a pull request. The "
            "developer has written the following Python function:\n\n"
            "```python\n"
            "def get_user(id):\n"
            "    result = db.execute(f'SELECT * FROM users WHERE id = {id}')\n"
            "    return result.fetchone()\n"
            "```\n\n"
            "What are the issues with this code and how would you fix them?"
        ),
        "completion": (
            "This code has two critical problems:\n\n"
            "**1. SQL Injection vulnerability** — Interpolating `id` directly into "
            "the query string allows an attacker to pass a value like "
            "`1; DROP TABLE users;--` and execute arbitrary SQL. Fix this by using "
            "parameterised queries:\n\n"
            "```python\n"
            "result = db.execute('SELECT * FROM users WHERE id = :id', {'id': id})\n"
            "```\n\n"
            "**2. Missing type annotation and no error handling** — Without a type "
            "hint, callers don't know what `id` expects. If the row doesn't exist, "
            "`fetchone()` returns `None` silently, which will cause a confusing "
            "`AttributeError` downstream:\n\n"
            "```python\n"
            "def get_user(user_id: int) -> dict | None:\n"
            "    row = db.execute(\n"
            "        'SELECT * FROM users WHERE id = :id', {'id': user_id}\n"
            "    ).fetchone()\n"
            "    return dict(row) if row else None\n"
            "```"
        ),
        "prompt_tokens": 115,
        "completion_tokens": 198,
        "latency_ms": 1240,
    },
    {
        "feature": "summarize",
        "model": "gpt-4o",
        "prompt": (
            "Extract the three most important action items from the following "
            "meeting transcript as a bullet list:\n\n"
            "Alice: We need to ship the new onboarding flow by end of Q3. Bob, can "
            "you own that?\nBob: Sure. I'll need design sign-off from Carol first.\n"
            "Carol: I can get designs to Bob by Friday.\nAlice: Great. Also, the "
            "infra team flagged that our p99 latency on the /search endpoint is "
            "above SLA. Dave, please investigate and report back by next Tuesday.\n"
            "Dave: Understood. Finally, we still haven't renewed the Datadog "
            "contract — that expires in two weeks. Alice, can you loop in finance?\n"
            "Alice: I'll handle that today."
        ),
        "completion": (
            "• **Bob** to complete the new onboarding flow by end of Q3, pending "
            "design sign-off from Carol (designs due Friday).\n"
            "• **Dave** to investigate /search p99 latency and report back by next "
            "Tuesday.\n"
            "• **Alice** to contact finance today to renew the Datadog contract "
            "before it expires in two weeks."
        ),
        "prompt_tokens": 163,
        "completion_tokens": 72,
        "latency_ms": 610,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def _warn(msg: str) -> None:
    print(f"  [warn] {msg}")


def _cost(prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Estimate cost_usd: prompt @ $0.000003/tok, completion @ $0.000015/tok."""
    return Decimal(str(round(
        prompt_tokens * 0.000003 + completion_tokens * 0.000015,
        6,
    )))


# ---------------------------------------------------------------------------
# Trace seeding function (isolated — does not touch Phase 2/3 logic)
# ---------------------------------------------------------------------------


async def _seed_traces(
    session,
    project: Project,
    dev_env: Environment,
    api_key: APIKey,
    org_id,
) -> None:
    """Insert 5 sample traces if none yet exist for the demo project.

    No audit events are emitted — these are fixture records, not user actions.
    """
    print("\n==> Sample traces")

    # Idempotency check: skip if any trace already exists for this project
    count_result = await session.execute(
        select(func.count()).select_from(Trace).where(Trace.project_id == project.id)
    )
    existing_count: int = count_result.scalar() or 0
    if existing_count > 0:
        _skip(f"{existing_count} trace(s) already exist for project '{project.slug}' — skipping.")
        return

    trace_repo = TraceRepository(session)

    for i, spec in enumerate(_SAMPLE_TRACES, start=1):
        cost = _cost(spec["prompt_tokens"], spec["completion_tokens"])
        total = spec["prompt_tokens"] + spec["completion_tokens"]

        await trace_repo.create(
            organization_id=org_id,
            project_id=project.id,
            environment_id=dev_env.id,
            api_key_id=api_key.id,
            feature=spec["feature"],
            model=spec["model"],
            prompt=spec["prompt"],
            completion=spec["completion"],
            prompt_tokens=spec["prompt_tokens"],
            completion_tokens=spec["completion_tokens"],
            total_tokens=total,
            latency_ms=spec["latency_ms"],
            cost_usd=cost,
            prompt_version="v1",
            metadata_json={"seed": True, "index": i},
        )

    await session.commit()
    _ok(f"Inserted {len(_SAMPLE_TRACES)} sample traces for project '{project.slug}'.")


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
            seeded_api_key = existing_key
        else:
            seeded_api_key, plaintext_key = await api_key_svc.create_api_key(
                project_id=project.id,
                environment_id=dev_env.id,
                name=API_KEY_NAME,
            )
            _ok(
                f"Created API key '{API_KEY_NAME}' "
                f"(prefix={seeded_api_key.key_prefix}, id={seeded_api_key.id})"
            )

        # ------------------------------------------------------------------
        # 6. Sample traces  (Phase 4 — idempotent, no audit events)
        # ------------------------------------------------------------------
        await _seed_traces(
            session=session,
            project=project,
            dev_env=dev_env,
            api_key=seeded_api_key,
            org_id=org.id,
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
