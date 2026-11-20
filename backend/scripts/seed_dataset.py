"""
seed_dataset.py — Phase 4 demo dataset seed script.

Creates a 'sentiment-golden' dataset with 5 annotated rows (3 positive,
2 negative) under the seeded Acme / demo project from seed_data.py.

Usage (from backend/ directory):
    python -m scripts.seed_dataset

Re-running is safe:
- If the dataset already exists it is reused.
- If an identical file was already uploaded the existing version is returned
  with ``duplicate=True`` and no new row is written.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure backend/ is on sys.path when run as a script.
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.dataset import Dataset
from app.models.enums import EnvironmentName
from app.models.environment import Environment
from app.models.organization import Organization
from app.models.project import Project
from app.services import dataset_service

# ---------------------------------------------------------------------------
# Seed constants — must match scripts/seed_data.py
# ---------------------------------------------------------------------------
_ORG_SLUG = "acme"
_PROJECT_SLUG = "demo"
_DATASET_NAME = "sentiment-golden"

# ---------------------------------------------------------------------------
# 5-row sentiment golden set (3 positive, 2 negative)
# ---------------------------------------------------------------------------
_ROWS = [
    {
        "input": "The product arrived on time and works perfectly. Highly recommend!",
        "expected": "POSITIVE",
        "metadata": {"category": "product", "source": "review-site"},
    },
    {
        "input": "Absolutely love this service. The team was helpful and responsive.",
        "expected": "POSITIVE",
        "metadata": {"category": "service", "source": "survey"},
    },
    {
        "input": "Great value for money. Would buy again without hesitation.",
        "expected": "POSITIVE",
        "metadata": {"category": "product", "source": "review-site"},
    },
    {
        "input": "The delivery was late and the packaging was damaged. Very disappointed.",
        "expected": "NEGATIVE",
        "metadata": {"category": "logistics", "source": "support-ticket"},
    },
    {
        "input": "Terrible customer service. My issue was ignored for two weeks.",
        "expected": "NEGATIVE",
        "metadata": {"category": "service", "source": "support-ticket"},
    },
]

_JSONL_BYTES: bytes = b"\n".join(
    json.dumps(row).encode() for row in _ROWS
) + b"\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


async def _resolve_org_and_project(db):
    """Return (org, project) for the seeded Acme demo data."""
    org_row = await db.execute(
        select(Organization).where(Organization.slug == _ORG_SLUG)
    )
    org: Organization | None = org_row.scalars().first()
    if org is None:
        print(
            f"[error] Organisation '{_ORG_SLUG}' not found. "
            "Run `python -m scripts.seed_data` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    proj_row = await db.execute(
        select(Project).where(
            Project.organization_id == org.id,
            Project.slug == _PROJECT_SLUG,
        )
    )
    project: Project | None = proj_row.scalars().first()
    if project is None:
        print(
            f"[error] Project '{_PROJECT_SLUG}' not found. "
            "Run `python -m scripts.seed_data` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    return org, project


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print(f"\n{'=' * 60}")
    print("  Prism — Phase 4 Dataset Seed")
    print(f"{'=' * 60}\n")

    async with async_session_factory() as db:
        org, project = await _resolve_org_and_project(db)

        # ----------------------------------------------------------------
        # Resolve or create the dataset
        # ----------------------------------------------------------------
        print("==> Dataset")
        ds_row = await db.execute(
            select(Dataset).where(
                Dataset.org_id == org.id,
                Dataset.project_id == project.id,
                Dataset.name == _DATASET_NAME,
            )
        )
        dataset = ds_row.scalars().first()

        if dataset is not None:
            _skip(f"Dataset '{_DATASET_NAME}' already exists (id={dataset.id})")
        else:
            dataset = await dataset_service.create_dataset(
                db,
                org_id=org.id,
                project_id=project.id,
                name=_DATASET_NAME,
            )
            _ok(f"Created dataset '{_DATASET_NAME}' (id={dataset.id})")

        # ----------------------------------------------------------------
        # Upload the golden JSONL
        # ----------------------------------------------------------------
        print("\n==> Version upload")
        version, was_duplicate = await dataset_service.upload_version(
            db,
            dataset_id=dataset.id,
            org_id=org.id,
            file_bytes=_JSONL_BYTES,
        )

        if was_duplicate:
            _skip(
                f"Identical file already stored as version {version.version_number} — no new version written."
            )
        else:
            _ok(f"Uploaded version {version.version_number} ({version.row_count} rows)")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print(f"\n{'─' * 60}")
    print(f"  dataset_id     : {dataset.id}")
    print(f"  version_number : {version.version_number}")
    print(f"  content_hash   : {version.content_hash}")
    print(f"  row_count      : {version.row_count}")
    print(f"  duplicate      : {was_duplicate}")
    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
