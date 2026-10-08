"""Generic base repository for asynchronous SQLAlchemy 2.x operations."""

from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.exceptions import NotFoundError

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic repository providing standardized asynchronous database CRUD operations."""

    def __init__(self, model: Type[T], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_or_none(self, id: Any) -> Optional[T]:
        """Fetch a single record by primary key ID, or None if not found."""
        stmt = select(self.model).where(getattr(self.model, "id") == id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # Alias for get_or_none
    get_by_id = get_or_none

    async def get(self, id: Any) -> T:
        """Fetch a single record by primary key ID, raising NotFoundError if missing."""
        instance = await self.get_or_none(id)
        if instance is None:
            raise NotFoundError(f"{self.model.__name__} with id '{id}' not found.")
        return instance

    async def list(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> tuple[Sequence[T], int]:
        """List records with pagination and optional equality filters.

        Returns:
            A tuple of (items, total_count).
        """
        filters = filters or {}
        conditions = []
        for field, value in filters.items():
            if hasattr(self.model, field) and value is not None:
                conditions.append(getattr(self.model, field) == value)

        # Count total matching records
        count_stmt = select(func.count()).select_from(self.model)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total_count = (await self.session.execute(count_stmt)).scalar() or 0

        # Query paginated items
        items_stmt = select(self.model)
        if conditions:
            items_stmt = items_stmt.where(*conditions)
        items_stmt = items_stmt.offset(offset).limit(limit)
        result = await self.session.execute(items_stmt)
        items = result.scalars().all()

        return items, total_count

    async def count(self, filters: Optional[dict[str, Any]] = None) -> int:
        """Count total records matching optional equality filters."""
        filters = filters or {}
        conditions = []
        for field, value in filters.items():
            if hasattr(self.model, field) and value is not None:
                conditions.append(getattr(self.model, field) == value)

        stmt = select(func.count()).select_from(self.model)
        if conditions:
            stmt = stmt.where(*conditions)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def create(self, **kwargs: Any) -> T:
        """Instantiate, persist, flush, refresh, and return a new entity."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: T, **kwargs: Any) -> T:
        """Update fields on an existing entity instance, flush, refresh, and return."""
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: T) -> None:
        """Delete an existing entity from the database session and flush."""
        await self.session.delete(instance)
        await self.session.flush()

    async def flush(self) -> None:
        """Flush pending changes to the database."""
        await self.session.flush()

    async def commit(self) -> None:
        """Commit the current database transaction."""
        await self.session.commit()
