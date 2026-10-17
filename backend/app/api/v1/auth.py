"""Auth API endpoints — registration, login, and user profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Register a new user into an existing organization.",
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Register a new user account within an existing organization."""
    service = AuthService(db)
    return await service.register(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description="Verify credentials and issue a signed JWT access token.",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Verify user credentials and return an access token."""
    service = AuthService(db)
    user = await service.authenticate(
        email=str(payload.email),
        password=payload.password,
        organization_slug=payload.organization_slug,
    )
    return service.issue_token(user)


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Return the profile of the currently authenticated user.",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    """Return the currently authenticated user profile."""
    return current_user


__all__ = ["router"]
