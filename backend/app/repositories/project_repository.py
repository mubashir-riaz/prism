"""Project repository for database operations."""

from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository handling database operations for Project entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Project, session)

    async def get_by_slug(self, org_id: Any, slug: str) -> Optional[Project]:
        """Fetch a project by organization ID and unique slug."""
        stmt = select(self.model).where(
            self.model.organization_id == org_id,
            self.model.slug == slug,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_with_environments(self, project_id: Any) -> Optional[Project]:
        """Fetch a project with its environments eagerly loaded."""
        stmt = (
            select(self.model)
            .options(selectinload(self.model.environments))
            .where(self.model.id == project_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_org(
        self,
        org_id: Any,
        offset: int = 0,
        limit: int = 100,
        is_archived: Optional[bool] = None,
    ) -> tuple[Sequence[Project], int]:
        """List projects belonging to an organization, returning (items, total_count)."""
        filters: dict[str, Any] = {"organization_id": org_id}
        if is_archived is not None:
            filters["is_archived"] = is_archived
        return await self.list(offset=offset, limit=limit, filters=filters)
