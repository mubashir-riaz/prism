"""AuditLog business logic service."""

from typing import Any, Optional, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    """Write-only service encapsulating audit log append operations.
    
    Audit logs are strictly append-only; update and delete operations are prohibited.
    """

    def __init__(self, session_or_repo: Union[AsyncSession, AuditLogRepository]) -> None:
        if isinstance(session_or_repo, AuditLogRepository):
            self.repo = session_or_repo
        else:
            self.repo = AuditLogRepository(session_or_repo)

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
    ) -> AuditLog:
        """Record an immutable, append-only audit event in the system.

        Args:
            org_id: Organization ID where the event took place.
            actor_id: User ID who initiated the event, or None for system actions.
            action: Domain audit action type (AuditAction or string).
            resource_type: Target entity/resource type (e.g., 'project', 'api_key').
            resource_id: Target entity UUID, or None if not applicable.
            metadata: Additional contextual payload for the event.
            ip: Originating client IP address.
            ua: Originating client User-Agent string.

        Returns:
            The newly created and persisted AuditLog record.
        """
        parsed_org_id = uuid.UUID(str(org_id)) if isinstance(org_id, str) else org_id
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
            ip_address=ip,
            user_agent=ua,
        )
