"""APIKey repository for database operations."""

from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.repositories.base import BaseRepository


class APIKeyRepository(BaseRepository[APIKey]):
    """Repository handling database operations for APIKey entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(APIKey, session)

    async def get_by_prefix(self, prefix: str) -> Optional[APIKey]:
        """Fetch an API key record by its public prefix."""
        stmt = select(self.model).where(self.model.key_prefix == prefix)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_hash(self, hashed_key: str) -> Optional[APIKey]:
        """Fetch an API key record by its hashed key value."""
        stmt = select(self.model).where(self.model.hashed_key == hashed_key)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_project(
        self,
        project_id: Any,
        offset: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[Sequence[APIKey], int]:
        """List API keys belonging to a project, returning (items, total_count)."""
        filters: dict[str, Any] = {"project_id": project_id}
        if is_active is not None:
            filters["is_active"] = is_active
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_by_environment(
        self,
        environment_id: Any,
        offset: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[Sequence[APIKey], int]:
        """List API keys belonging to an environment, returning (items, total_count)."""
        filters: dict[str, Any] = {"environment_id": environment_id}
        if is_active is not None:
            filters["is_active"] = is_active
        return await self.list(offset=offset, limit=limit, filters=filters)
