"""User business logic service."""

from typing import Optional, Sequence, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    """Service encapsulating user management and business operations."""

    def __init__(self, session_or_repo: Union[AsyncSession, UserRepository]) -> None:
        if isinstance(session_or_repo, UserRepository):
            self.repo = session_or_repo
        else:
            self.repo = UserRepository(session_or_repo)

    async def create_user(
        self,
        org_id: Union[uuid.UUID, str],
        email: str,
        role: UserRole = UserRole.MEMBER,
        full_name: Optional[str] = None,
    ) -> User:
        """Create a new user within an organization after checking email uniqueness.

        Note: Password handling and hashing will be wired in Phase 3.
        """
        existing = await self.repo.get_by_email(email)
        if existing:
            raise ConflictError(f"User with email '{email}' already exists.")

        return await self.repo.create(
            organization_id=org_id,
            email=email,
            role=role,
            full_name=full_name,
            hashed_password="",
        )

    async def create_from_schema(self, data: UserCreate) -> User:
        """Helper to create a user directly from a UserCreate schema."""
        return await self.create_user(
            org_id=data.organization_id,
            email=data.email,
            role=data.role,
            full_name=data.full_name,
        )

    async def get_user(self, id: Union[uuid.UUID, str]) -> User:
        """Retrieve a user by their ID, raising NotFoundError if missing."""
        return await self.repo.get(id)

    async def get_user_by_email(self, email: str) -> User:
        """Retrieve a user by their email address, raising NotFoundError if missing."""
        user = await self.repo.get_by_email(email)
        if not user:
            raise NotFoundError(f"User with email '{email}' not found.")
        return user

    async def list_users_in_org(
        self,
        org_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """List all users belonging to an organization, returning (items, total_count)."""
        return await self.repo.list_by_org(org_id=org_id, offset=offset, limit=limit)

    async def deactivate_user(self, id: Union[uuid.UUID, str]) -> User:
        """Deactivate a user account by setting is_active to False."""
        user = await self.get_user(id)
        return await self.repo.update(user, is_active=False)

    async def update_user(self, id: Union[uuid.UUID, str], data: UserUpdate) -> User:
        """Update user profile or role details."""
        user = await self.get_user(id)
        update_data = data.model_dump(exclude_unset=True)
        return await self.repo.update(user, **update_data)
