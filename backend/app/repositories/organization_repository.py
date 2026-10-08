"""Organization repository for database operations."""

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Repository handling database operations for Organization entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Organization, session)

    async def get_by_slug(self, slug: str) -> Optional[Organization]:
        """Fetch an organization by its unique slug."""
        stmt = select(self.model).where(self.model.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_active(
        self, offset: int = 0, limit: int = 100
    ) -> tuple[Sequence[Organization], int]:
        """List active organizations with pagination, returning (items, total_count)."""
        return await self.list(offset=offset, limit=limit, filters={"is_active": True})
