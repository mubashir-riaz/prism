"""AuditLog business logic service."""

from typing import Any, Optional, Sequence, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    """Service encapsulating audit log append operations and resource queries.

    Audit logs are strictly append-only; update and delete operations are prohibited.
    Adheres to unit-of-work semantics: commits at the end of a successful operation,
    and rolls back on exception.
    """

    def __init__(self, session: Union[AsyncSession, AuditLogRepository]) -> None:
        if isinstance(session, AuditLogRepository):
            self.repo = session
        else:
            self.repo = AuditLogRepository(session)

    async def record(
        self,
        org_id: Union[uuid.UUID, str],
        actor_id: Optional[Union[uuid.UUID, str]],
        action: Union[AuditAction, str],
        resource_type: str,
        resource_id: Optional[Union[uuid.UUID, str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        ip: Optional[str] = None,
        ua: Optional[str] = None,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """Record an immutable, append-only audit event in the system.

        Args:
            org_id: Organization ID where the event took place.
            actor_id: User ID who initiated the event, or None for system actions.
            action: Domain audit action type (AuditAction or string).
            resource_type: Target entity/resource type (e.g., 'project', 'api_key', 'user').
            resource_id: Target entity UUID, or None if not applicable.
            metadata: Additional contextual payload for the event.
            ip: Originating client IP address.
            ua: Originating client User-Agent string.
            ip_address: Optional alias for ip.
            user_agent: Optional alias for ua.

        Returns:
            The newly created and persisted AuditLog record.
        """
        client_ip = ip or ip_address
        client_ua = ua or user_agent
        async with self.repo.transaction():
            parsed_org_id = uuid.UUID(str(org_id)) if isinstance(org_id, str) and org_id else org_id
            parsed_actor_id = uuid.UUID(str(actor_id)) if isinstance(actor_id, str) and actor_id else actor_id
            parsed_resource_id = uuid.UUID(str(resource_id)) if isinstance(resource_id, str) and resource_id else resource_id
            parsed_action = AuditAction(action) if isinstance(action, str) else action

            return await self.repo.create(
                organization_id=parsed_org_id,
                actor_user_id=parsed_actor_id,
                action=parsed_action,
                resource_type=resource_type,
                resource_id=parsed_resource_id,
                metadata_json=metadata or {},
                ip_address=client_ip,
                user_agent=client_ua,
            )

    async def list_for_resource(
        self,
        resource_type: str,
        resource_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[AuditLog], int]:
        """List audit logs targeting a specific resource, returning (items, total_count).

        Args:
            resource_type: Target entity/resource type (e.g. 'user', 'project', 'api_key').
            resource_id: Target entity UUID or string identifier.
            offset: Pagination offset.
            limit: Maximum number of records to return.

        Returns:
            A tuple of (items, total_count).
        """
        return await self.repo.list_by_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            offset=offset,
            limit=limit,
        )

    async def list_for_organization(
        self,
        organization_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
    ) -> tuple[Sequence[AuditLog], int]:
        """List audit logs for an organization with pagination, returning (items, total_count)."""
        return await self.repo.list_by_organization(
            organization_id=organization_id,
            offset=offset,
            limit=limit,
            action=action,
            resource_type=resource_type,
        )
