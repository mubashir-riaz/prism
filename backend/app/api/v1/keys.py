"""API key management endpoints — create, list, and revoke."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.exceptions import AuthError, NotFoundError
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.api_key import APIKeyCreate, APIKeyCreateResponse, APIKeyRead
from app.services.api_key_service import APIKeyService

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enforce_role(user: User) -> None:
    """Raise AuthError if the user is not OWNER or ADMIN."""
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise AuthError("insufficient permissions")


async def _get_project_or_403(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Verify the project exists and belongs to the caller's organization."""
    repo = ProjectRepository(db)
    project = await repo.get_or_none(project_id)
    if project is None:
        raise NotFoundError(f"Project with id '{project_id}' not found.")
    if str(project.organization_id) != str(user.organization_id):
        raise AuthError("insufficient permissions")


# ---------------------------------------------------------------------------
# POST /v1/keys — create a new API key
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    description="Create a new API key for a project/environment. "
    "The plaintext key is returned **once** in the response and cannot be retrieved again.",
)
async def create_key(
    payload: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyCreateResponse:
    """Create a new API key, returning the one-time plaintext value."""
    _enforce_role(current_user)
    await _get_project_or_403(payload.project_id, current_user, db)

    service = APIKeyService(db)
    record, plaintext = await service.create_api_key(
        project_id=payload.project_id,
        environment_id=payload.environment_id,
        name=payload.name,
        actor_user_id=current_user.id,
    )

    return APIKeyCreateResponse(
        id=record.id,
        project_id=record.project_id,
        environment_id=record.environment_id,
        name=record.name,
        key_prefix=record.key_prefix,
        is_active=record.is_active,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        plaintext_key=plaintext,
    )


# ---------------------------------------------------------------------------
# GET /v1/keys — list keys for a project
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[APIKeyRead],
    status_code=status.HTTP_200_OK,
    summary="List API keys",
    description="List API key metadata for a project. Never returns the hashed key or plaintext.",
)
async def list_keys(
    project_id: uuid.UUID = Query(..., description="Project to list keys for"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Page size"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[APIKeyRead]:
    """Return key metadata for all keys belonging to the project."""
    _enforce_role(current_user)
    await _get_project_or_403(project_id, current_user, db)

    service = APIKeyService(db)
    items, _ = await service.list_keys_for_project(
        project_id,
        offset=offset,
        limit=limit,
        is_active=is_active,
    )
    return [APIKeyRead.model_validate(k) for k in items]


# ---------------------------------------------------------------------------
# DELETE /v1/keys/{id} — revoke a key
# ---------------------------------------------------------------------------


@router.delete(
    "/{id}",
    response_model=APIKeyRead,
    status_code=status.HTTP_200_OK,
    summary="Revoke an API key",
    description="Revoke an API key by setting is_active=False and recording revoked_at.",
)
async def revoke_key(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyRead:
    """Revoke an API key and emit an audit event."""
    _enforce_role(current_user)

    service = APIKeyService(db)
    # Fetch the key first to verify org ownership
    key = await service.get_api_key(id)
    await _get_project_or_403(key.project_id, current_user, db)

    revoked = await service.revoke_api_key(id, actor_user_id=current_user.id)
    return APIKeyRead.model_validate(revoked)


__all__ = ["router"]
