"""Authentication and authorization dependencies for Prism API."""

from __future__ import annotations

from typing import Callable
import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.exceptions import AuthError, TokenError
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository

# OAuth2 password bearer token scheme pointing to the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate JWT access token and return the authenticated active user.

    Raises:
        TokenError: If token is missing, expired, or contains an invalid subject.
        AuthError: If the user does not exist or is inactive.
    """
    payload = decode_access_token(token)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise TokenError("Token is missing subject claim.")

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise TokenError("Token subject is not a valid UUID.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_uuid)
    if user is None:
        raise AuthError("User not found.")

    if not user.is_active:
        raise AuthError("User is inactive.")

    return user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory returning a dependency that enforces the current user has one of *roles*.

    Raises:
        AuthError: If the authenticated user's role is not included in *roles.
    """
    async def _role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in roles:
            raise AuthError("insufficient permissions")
        return current_user

    return _role_checker


__all__ = [
    "oauth2_scheme",
    "get_current_user",
    "require_role",
]
