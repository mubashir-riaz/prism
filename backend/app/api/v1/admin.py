"""Admin-only endpoints for Prism.

# DEV-ONLY:
# This module contains smoke test routes for verifying RBAC.
# It is not a product feature and will be removed in Phase 22 (middleware hardening)
# if it stops being useful.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.api.deps import require_role
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter()


class AdminPingResponse(BaseModel):
    """Response schema for admin RBAC sanity check route."""

    pong: bool = Field(..., description="Sanity ping acknowledgment.")
    role: str = Field(..., description="Role of the authenticated caller.")


# DEV-ONLY: Smoke test route for RBAC verification
@router.get(
    "/ping",
    response_model=AdminPingResponse,
    status_code=status.HTTP_200_OK,
    summary="RBAC sanity ping (dev-only)",
    description="Admin-only smoke test route for testing RBAC permissions.",
)
async def admin_ping(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
) -> AdminPingResponse:
    """Admin-only sanity ping endpoint for testing RBAC.

    # DEV-ONLY: Smoke test route, not a product feature.
    Will be removed in Phase 22 (middleware hardening) if it stops being useful.
    """
    role_name = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    return AdminPingResponse(pong=True, role=role_name)


__all__ = ["router", "AdminPingResponse"]
