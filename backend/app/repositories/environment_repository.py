"""Environment repository for database operations."""

from typing import Any, Optional, Sequence, Union

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName
from app.models.environment import Environment
from app.repositories.base import BaseRepository


class EnvironmentRepository(BaseRepository[Environment]):
    """Repository handling database operations for Environment entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Environment, session)

    async def get_by_name(
        self, project_id: Any, name: Union[EnvironmentName, str]
    ) -> Optional[Environment]:
        """Fetch an environment by project ID and environment name."""
        stmt = select(self.model).where(
            self.model.project_id == project_id,
            self.model.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_default(self, project_id: Any) -> Optional[Environment]:
        """Fetch the default environment for a project."""
        stmt = select(self.model).where(
            self.model.project_id == project_id,
            self.model.is_default.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_project(
        self,
        project_id: Any,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Environment], int]:
        """List all environments belonging to a project, returning (items, total_count)."""
        return await self.list(offset=offset, limit=limit, filters={"project_id": project_id})

    async def clear_default(self, project_id: Any) -> None:
        """Clear default status from all environments within a project."""
        stmt = (
            update(self.model)
            .where(self.model.project_id == project_id)
            .values(is_default=False)
        )
        await self.session.execute(stmt)
        await self.session.flush()
