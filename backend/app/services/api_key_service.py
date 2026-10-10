"""APIKey business logic service."""

from datetime import datetime, timezone
import hashlib
import secrets
from typing import Optional, Sequence, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.models.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository


class APIKeyService:
    """Service encapsulating API key creation, revocation, and metadata listing."""

    def __init__(self, session_or_repo: Union[AsyncSession, APIKeyRepository]) -> None:
        if isinstance(session_or_repo, APIKeyRepository):
            self.repo = session_or_repo
        else:
            self.repo = APIKeyRepository(session_or_repo)

    async def create_api_key(
        self,
        project_id: Union[uuid.UUID, str],
        environment_id: Union[uuid.UUID, str],
        name: str,
    ) -> tuple[APIKey, str]:
        """Create and persist an API key, returning the record and the unrecoverable plaintext key.

        The plaintext key is generated using secrets.token_urlsafe(32) and returned
        only once. Only the prefix and SHA256 hashed secret are stored in the database.
        """
        raw_secret = secrets.token_urlsafe(32)
        key_prefix = f"prism_{raw_secret[:8]}"
        plaintext_key = f"{key_prefix}_{raw_secret[8:]}"
        hashed_key = hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()

        record = await self.repo.create(
            project_id=project_id,
            environment_id=environment_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
            is_active=True,
        )

        return record, plaintext_key

    async def get_api_key(self, id: Union[uuid.UUID, str]) -> APIKey:
        """Retrieve an API key by its ID, raising NotFoundError if missing."""
        return await self.repo.get(id)

    async def revoke_api_key(self, id: Union[uuid.UUID, str]) -> APIKey:
        """Revoke an API key by setting is_active to False and revoked_at to current timestamp."""
        key = await self.get_api_key(id)
        now = datetime.now(timezone.utc)
        return await self.repo.update(key, is_active=False, revoked_at=now)

    async def list_keys_for_project(
        self,
        project_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[Sequence[APIKey], int]:
        """List metadata for all API keys belonging to a project with pagination."""
        return await self.repo.list_by_project(
            project_id,
            offset=offset,
            limit=limit,
            is_active=is_active,
        )

    async def list_keys_for_environment(
        self,
        environment_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[Sequence[APIKey], int]:
        """List metadata for all API keys belonging to an environment with pagination."""
        return await self.repo.list_by_environment(
            environment_id,
            offset=offset,
            limit=limit,
            is_active=is_active,
        )

    async def record_usage(self, id: Union[uuid.UUID, str]) -> APIKey:
        """Record the last used timestamp for an API key."""
        key = await self.get_api_key(id)
        return await self.repo.update(key, last_used_at=datetime.now(timezone.utc))
