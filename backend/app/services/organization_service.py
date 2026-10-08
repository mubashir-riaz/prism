"""Organization business logic service."""

from typing import Optional, Sequence, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError
from app.models.organization import Organization
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import OrganizationCreate, OrganizationUpdate


class OrganizationService:
    """Service encapsulating business operations and validation for organizations."""

    def __init__(self, session_or_repo: Union[AsyncSession, OrganizationRepository]) -> None:
        if isinstance(session_or_repo, OrganizationRepository):
            self.repo = session_or_repo
        else:
            self.repo = OrganizationRepository(session_or_repo)

    async def create_organization(self, data: OrganizationCreate) -> Organization:
        """Create a new organization, ensuring slug uniqueness."""
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise ConflictError(f"Organization with slug '{data.slug}' already exists.")

        return await self.repo.create(name=data.name, slug=data.slug)

    async def get_organization(self, id: Union[uuid.UUID, str]) -> Organization:
        """Retrieve an organization by its ID, raising NotFoundError if missing."""
        return await self.repo.get(id)

    async def get_organization_by_slug(self, slug: str) -> Organization:
        """Retrieve an organization by its slug, raising NotFoundError if missing."""
        org = await self.repo.get_by_slug(slug)
        if not org:
            raise NotFoundError(f"Organization with slug '{slug}' not found.")
        return org

    async def update_organization(
        self, id: Union[uuid.UUID, str], data: OrganizationUpdate
    ) -> Organization:
        """Update an organization's details, checking for slug uniqueness if slug is changed."""
        org = await self.get_organization(id)
        update_data = data.model_dump(exclude_unset=True)

        if "slug" in update_data and update_data["slug"] != org.slug:
            existing = await self.repo.get_by_slug(update_data["slug"])
            if existing and existing.id != org.id:
                raise ConflictError(f"Organization with slug '{update_data['slug']}' already exists.")

        return await self.repo.update(org, **update_data)

    async def deactivate_organization(self, id: Union[uuid.UUID, str]) -> Organization:
        """Deactivate an organization by setting is_active to False."""
        org = await self.get_organization(id)
        return await self.repo.update(org, is_active=False)

    async def list_organizations(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None,
    ) -> tuple[Sequence[Organization], int]:
        """List all organizations with pagination, returning (items, total_count)."""
        return await self.repo.list(offset=offset, limit=limit, filters=filters)

    async def list_active_organizations(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Organization], int]:
        """List active organizations with pagination, returning (items, total_count)."""
        return await self.repo.list_active(offset=offset, limit=limit)
