"""Trace repository for database operations."""

from typing import Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trace import Trace
from app.repositories.base import BaseRepository


class TraceRepository(BaseRepository[Trace]):
    """Repository handling database operations for Trace entities.

    All scoped lookups include ``organization_id`` in the WHERE clause so
    cross-org ID probing returns ``None`` instead of leaking data.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Trace, session)

    async def get_by_id_for_org(
        self,
        trace_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Trace | None:
        """Fetch a trace by primary key scoped to a specific organization.

        Returns ``None`` when the trace does not exist *or* belongs to a
        different organization — callers must not distinguish the two cases
        to avoid information leakage.
        """
        stmt = select(self.model).where(
            self.model.id == trace_id,
            self.model.organization_id == organization_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Trace], int]:
        """List traces belonging to a project ordered by recency, returning (items, total_count).

        Results are ordered by ``created_at DESC`` so the newest trace is first,
        which aligns with the ``ix_traces_project_id_created_at`` composite index.
        """
        # Count total matching records for pagination metadata
        count_stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.project_id == project_id)
        )
        total: int = (await self.session.execute(count_stmt)).scalar() or 0

        # Fetch the requested page, newest first
        items_stmt = (
            select(self.model)
            .where(self.model.project_id == project_id)
            .order_by(self.model.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(items_stmt)
        items: list[Trace] = list(result.scalars().all())

        return items, total

    async def count_by_project(self, project_id: uuid.UUID) -> int:
        """Return the total number of traces belonging to a project."""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.project_id == project_id)
        )
        return (await self.session.execute(stmt)).scalar() or 0
