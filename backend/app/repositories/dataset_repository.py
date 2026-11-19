"""Repository for Dataset and DatasetVersion database operations."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion


class DatasetRepository:
    """Data-access layer for datasets and their versions.

    Design rules
    ------------
    * Every dataset lookup filters on BOTH ``id`` AND ``org_id`` — isolation
      is enforced in the query itself, never delegated to the caller.
    * ``IntegrityError`` is intentionally NOT caught here.  The service layer
      owns the duplicate/conflict logic and decides what error to surface.
    * All methods accept an explicit ``db: AsyncSession`` rather than storing
      one at construction time — this keeps the repository stateless and safe
      to reuse across request-scoped and background sessions.
    """

    # ------------------------------------------------------------------
    # Dataset methods
    # ------------------------------------------------------------------

    async def create_dataset(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
    ) -> Dataset:
        """Insert and return a new Dataset row.

        The unique constraint ``(org_id, project_id, name)`` on the table
        means a duplicate name within the same project raises
        ``sqlalchemy.exc.IntegrityError`` — the caller is responsible for
        catching this.
        """
        dataset = Dataset(
            org_id=org_id,
            project_id=project_id,
            name=name,
        )
        db.add(dataset)
        await db.flush()
        await db.refresh(dataset)
        return dataset

    async def get_dataset(
        self,
        db: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> Dataset | None:
        """Fetch a Dataset by primary key, scoped to the caller's organisation.

        Returns ``None`` when the dataset does not exist **or** belongs to a
        different org — callers must not distinguish the two cases to prevent
        cross-org enumeration attacks.
        """
        stmt = select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.org_id == org_id,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_datasets(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> list[Dataset]:
        """Return all datasets visible to an organisation.

        When ``project_id`` is supplied the results are further filtered to
        that project.  Results are ordered by name ascending for stable
        pagination in the future.
        """
        stmt = select(Dataset).where(Dataset.org_id == org_id)
        if project_id is not None:
            stmt = stmt.where(Dataset.project_id == project_id)
        stmt = stmt.order_by(Dataset.name.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # DatasetVersion methods
    # ------------------------------------------------------------------

    async def create_version(
        self,
        db: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        version_number: int,
        content_hash: str,
        row_count: int,
        rows: list[dict[str, Any]],
    ) -> DatasetVersion:
        """Insert and return a new DatasetVersion row.

        The unique constraints ``(dataset_id, version_number)`` and
        ``(dataset_id, content_hash)`` on the table mean a duplicate version
        or a duplicate file raises ``sqlalchemy.exc.IntegrityError`` — the
        caller is responsible for catching this.
        """
        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=version_number,
            content_hash=content_hash,
            row_count=row_count,
            rows=rows,
        )
        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version

    async def get_version_by_hash(
        self,
        db: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        content_hash: str,
    ) -> DatasetVersion | None:
        """Return the existing version with this content_hash, or ``None``.

        This is the idempotency check — the service calls this before
        attempting to insert a new version.
        """
        stmt = select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.content_hash == content_hash,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_version_by_number(
        self,
        db: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        version_number: int,
    ) -> DatasetVersion | None:
        """Return the version with this exact version_number, or ``None``."""
        stmt = select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version_number == version_number,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_versions(
        self,
        db: AsyncSession,
        *,
        dataset_id: uuid.UUID,
    ) -> list[DatasetVersion]:
        """Return all versions for a dataset, ordered by version_number ascending."""
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_version_number(
        self,
        db: AsyncSession,
        *,
        dataset_id: uuid.UUID,
    ) -> int | None:
        """Return the highest version_number for a dataset, or ``None`` if no versions exist.

        Uses ``SELECT MAX(version_number)`` so it works correctly even if
        version numbers are not perfectly contiguous (e.g. after a failed
        transaction left a gap).
        """
        stmt = select(func.max(DatasetVersion.version_number)).where(
            DatasetVersion.dataset_id == dataset_id,
        )
        result = await db.execute(stmt)
        return result.scalar()  # None when no rows match
