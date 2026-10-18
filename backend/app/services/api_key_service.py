"""APIKey business logic service."""

from datetime import datetime, timezone
from typing import Optional, Sequence, Union
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_api_key, verify_api_key
from app.exceptions import NotFoundError
from app.models.api_key import APIKey
from app.models.environment import Environment
from app.models.enums import AuditAction
from app.repositories.api_key_repository import APIKeyRepository
from app.services.audit_service import AuditService


class APIKeyService:
    """Service encapsulating API key creation, revocation, and metadata listing.
    
    Adheres to unit-of-work semantics: commits at the end of a successful operation,
    and rolls back on exception.
    """

    def __init__(self, session: Union[AsyncSession, APIKeyRepository]) -> None:
        if isinstance(session, APIKeyRepository):
            self.repo = session
            self._session = session.session
        else:
            self.repo = APIKeyRepository(session)
            self._session = session

    async def create_api_key(
        self,
        project_id: Union[uuid.UUID, str],
        environment_id: Union[uuid.UUID, str],
        name: str,
        actor_user_id: Optional[Union[uuid.UUID, str]] = None,
    ) -> tuple[APIKey, str]:
        """Create and persist an API key, returning the record and the unrecoverable plaintext key.

        The environment is loaded to determine the env string (dev/staging/prod).
        The plaintext key is generated via ``generate_api_key(env)`` from
        ``core/security.py`` and returned only once. Only the key prefix and
        SHA-256 hashed key are stored in the database.

        An ``AuditAction.KEY_CREATED`` event is emitted upon successful creation.
        """
        async with self.repo.transaction():
            # Load the environment with its project (eager) to get org_id for audit
            stmt = (
                select(Environment)
                .where(Environment.id == environment_id)
                .options(selectinload(Environment.project))
            )
            result = await self._session.execute(stmt)
            environment = result.scalars().first()
            if environment is None:
                raise NotFoundError(
                    f"Environment with id '{environment_id}' not found."
                )

            env_str = environment.name.value  # EnvironmentName enum → "dev"/"staging"/"prod"

            # Generate properly formatted API key
            plaintext, key_prefix, hashed_key = generate_api_key(env_str)

            record = await self.repo.create(
                project_id=project_id,
                environment_id=environment_id,
                name=name,
                key_prefix=key_prefix,
                hashed_key=hashed_key,
                is_active=True,
            )

            # Emit audit event
            audit_service = AuditService(self._session)
            await audit_service.record(
                org_id=environment.project.organization_id,
                actor_id=actor_user_id,
                action=AuditAction.KEY_CREATED,
                resource_type="api_key",
                resource_id=record.id,
                metadata={"key_prefix": key_prefix, "environment": env_str, "name": name},
            )

            return record, plaintext

    async def authenticate(self, plaintext_key: str) -> Optional[APIKey]:
        """Authenticate an API key by its plaintext value.

        Parse the key to extract the key_prefix (first three segments:
        ``prism_<env>_<prefix>``), look it up, and verify the hash.

        On success the caller should update ``last_used_at`` via the
        request-scoped session (do **not** commit inside this method).

        Returns the :class:`APIKey` record on success, or ``None`` if
        authentication fails (not found / inactive / revoked / hash mismatch).
        """
        # Key format: prism_<env>_<prefix12>_<secret32>
        parts = plaintext_key.split("_", 3)  # ['prism', '<env>', '<prefix12>', '<secret32>']
        if len(parts) != 4 or parts[0] != "prism":
            return None

        # key_prefix is the first three segments: prism_<env>_<prefix12>
        key_prefix = f"{parts[0]}_{parts[1]}_{parts[2]}"

        record = await self.repo.get_by_prefix(key_prefix)
        if record is None:
            return None

        # Reject inactive or revoked keys
        if not record.is_active or record.revoked_at is not None:
            return None

        # Timing-safe hash comparison
        if not verify_api_key(plaintext_key, record.hashed_key):
            return None

        # Update last_used_at — flushed but NOT committed here;
        # the request-scoped session will commit.
        record.last_used_at = datetime.now(timezone.utc)

        return record

    async def get_api_key(self, id: Union[uuid.UUID, str]) -> APIKey:
        """Retrieve an API key by its ID, raising NotFoundError if missing."""
        return await self.repo.get(id)

    async def revoke_api_key(self, id: Union[uuid.UUID, str]) -> APIKey:
        """Revoke an API key by setting is_active to False and revoked_at to current timestamp."""
        async with self.repo.transaction():
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
        async with self.repo.transaction():
            key = await self.get_api_key(id)
            return await self.repo.update(key, last_used_at=datetime.now(timezone.utc))
