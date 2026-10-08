"""User repository for database operations."""

from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository handling database operations for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by unique email address."""
        stmt = select(self.model).where(self.model.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_email_in_org(self, org_id: Any, email: str) -> Optional[User]:
        """Fetch a user by organization ID and email address."""
        stmt = select(self.model).where(
            self.model.organization_id == org_id,
            self.model.email == email,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_org(
        self,
        org_id: Any,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """List all users belonging to an organization, returning (items, total_count)."""
        return await self.list(offset=offset, limit=limit, filters={"organization_id": org_id})

    async def list_active_in_org(
        self,
        org_id: Any,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """List active users belonging to an organization, returning (items, total_count)."""
        return await self.list(
            offset=offset,
            limit=limit,
            filters={"organization_id": org_id, "is_active": True},
        )
