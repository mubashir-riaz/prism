"""Trace repository for database operations."""

from datetime import datetime
from typing import Sequence
import uuid

from sqlalchemy import func, select, tuple_
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

    async def list_traces(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        model: str | None = None,
        feature: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        limit: int = 50,
    ) -> tuple[list[Trace], bool]:
        """Return a page of traces scoped to an organisation, ordered created_at DESC, id DESC.

        Uses the n+1 trick — fetches ``limit + 1`` rows and uses the extra row
        to determine whether a next page exists, then strips it before returning.

        Args:
            db:      Async database session (used for the query; ``self.session``
                     is not used here so the same repo instance can serve both
                     request-scoped and background-task sessions).
            org_id:  Organisation whose traces to fetch. Never optional —
                     every query is scoped to prevent cross-org data leakage.
            model:   Optional exact-match filter on ``Trace.model``.
            feature: Optional exact-match filter on ``Trace.feature``.
            since:   Optional inclusive lower bound on ``Trace.created_at``.
            until:   Optional inclusive upper bound on ``Trace.created_at``.
            cursor:  Optional (created_at, id) pair from the last row of the
                     previous page.  Translated to a Postgres row-value
                     comparison: ``(created_at, id) < (cursor_ts, cursor_id)``.
            limit:   Maximum number of traces to return (default 50).

        Returns:
            A ``(traces, has_next)`` tuple where *traces* contains at most
            *limit* items and *has_next* is ``True`` when at least one more
            row exists beyond the returned page.
        """
        stmt = select(self.model).where(
            self.model.organization_id == org_id,
        )

        if model is not None:
            stmt = stmt.where(self.model.model == model)

        if feature is not None:
            stmt = stmt.where(self.model.feature == feature)

        if since is not None:
            stmt = stmt.where(self.model.created_at >= since)

        if until is not None:
            stmt = stmt.where(self.model.created_at <= until)

        if cursor is not None:
            cursor_ts, cursor_id = cursor
            # Postgres row-value comparison: (created_at, id) < (cursor_ts, cursor_id)
            # tuple_() emits the SQL ROW() / "(" col, col ")" syntax that Postgres
            # evaluates as a compound less-than, correctly handling ties on
            # created_at by falling through to the id tiebreaker.
            stmt = stmt.where(
                tuple_(self.model.created_at, self.model.id)
                < tuple_(cursor_ts, cursor_id)
            )

        stmt = (
            stmt.order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit + 1)
        )

        result = await db.execute(stmt)
        rows: list[Trace] = list(result.scalars().all())

        has_next = len(rows) > limit
        if has_next:
            rows = rows[:limit]

        return rows, has_next

    async def count_by_project(self, project_id: uuid.UUID) -> int:
        """Return the total number of traces belonging to a project."""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.project_id == project_id)
        )
        return (await self.session.execute(stmt)).scalar() or 0
