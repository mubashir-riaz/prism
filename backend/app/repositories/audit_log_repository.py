"""AuditLog repository for database operations."""

from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository handling database operations for immutable AuditLog entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AuditLog, session)

    async def update(self, instance: AuditLog, **kwargs: Any) -> AuditLog:
        """Audit logs are strictly append-only; updates are prohibited."""
        raise NotImplementedError("Audit logs are append-only and cannot be updated.")

    async def delete(self, instance: AuditLog) -> None:
        """Audit logs are strictly append-only; deletions are prohibited."""
        raise NotImplementedError("Audit logs are append-only and cannot be deleted.")

    async def list_by_organization(
        self,
        organization_id: Any,
        offset: int = 0,
        limit: int = 100,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
    ) -> tuple[Sequence[AuditLog], int]:
        """List audit logs for an organization with pagination, returning (items, total_count)."""
        filters: dict[str, Any] = {"organization_id": organization_id}
        if action is not None:
            filters["action"] = action
        if resource_type is not None:
            filters["resource_type"] = resource_type
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: Any,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[AuditLog], int]:
        """List audit logs targeting a specific resource, returning (items, total_count)."""
        filters: dict[str, Any] = {
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        return await self.list(offset=offset, limit=limit, filters=filters)
