"""Auth business logic service — registration, login, and token issuance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.exceptions import AuthError, ConflictError, NotFoundError
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegisterRequest, TokenResponse


class AuthService:
    """Service encapsulating registration, authentication, and token issuance.

    Follows the same unit-of-work pattern as Phase 2 services:
    - Constructed with an ``AsyncSession``.
    - Each mutating method owns its transaction via ``repo.transaction()``.
    - Commits on success, rolls back on any exception.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.user_repo = UserRepository(session)
        self.org_repo = OrganizationRepository(session)
        self.audit_repo = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def register(self, payload: RegisterRequest) -> User:
        """Register a new user inside an existing organisation.

        Steps
        -----
        1. Resolve org by ``organization_slug`` → :exc:`NotFoundError` if absent.
        2. Ensure email is unique within that org → :exc:`ConflictError` if taken.
        3. Hash the password with Argon2id.
        4. Persist the user with the requested role.
        5. Emit an ``AuditAction.CREATE`` event for ``resource_type="user"``.
        6. Commit and return the new :class:`User`.
        """
        async with self.user_repo.transaction():
            # 1. Resolve organisation
            org = await self.org_repo.get_by_slug(payload.organization_slug)
            if org is None:
                raise NotFoundError("Organization not found.")

            # 2. Email uniqueness within the org
            existing = await self.user_repo.get_by_email_in_org(org.id, payload.email)
            if existing is not None:
                raise ConflictError("Email already registered in this organization.")

            # 3. Hash password
            hashed = hash_password(payload.password)

            # 4. Persist user
            user = await self.user_repo.create(
                organization_id=org.id,
                email=str(payload.email),
                hashed_password=hashed,
                full_name=payload.full_name,
                role=payload.role,
            )

            # 5. Audit event
            await self.audit_repo.create(
                organization_id=org.id,
                actor_user_id=user.id,
                action=AuditAction.CREATE,
                resource_type="user",
                resource_id=user.id,
                metadata_json={"email": str(payload.email), "role": payload.role.value},
            )

            # 6. Commit happens when the transaction context manager exits cleanly
            return user

    async def authenticate(
        self,
        email: str,
        password: str,
        organization_slug: str | None = None,
    ) -> User:
        """Verify credentials and return the authenticated :class:`User`.

        ``organization_slug`` is optional. When supplied, the lookup is scoped
        to that organisation; otherwise the user is fetched by email directly.

        Raises :exc:`AuthError` (with the generic message "invalid credentials")
        on *any* failure: unknown org, unknown email, wrong password, or inactive
        account. This prevents user-enumeration via timing or distinct messages.
        """
        async with self.user_repo.transaction():
            if organization_slug:
                # Resolve org — failure is opaque to the caller
                org = await self.org_repo.get_by_slug(organization_slug)
                if org is None:
                    raise AuthError("Invalid credentials.")
                user = await self.user_repo.get_by_email_in_org(org.id, email)
            else:
                user = await self.user_repo.get_by_email(email)

            if user is None:
                raise AuthError("Invalid credentials.")

            # Account must be active
            if not user.is_active:
                raise AuthError("Invalid credentials.")

            # Password verification
            if not verify_password(password, user.hashed_password):
                raise AuthError("Invalid credentials.")

            # Update last_login_at
            user = await self.user_repo.update(
                user,
                last_login_at=datetime.now(timezone.utc),
            )

            # Audit event
            await self.audit_repo.create(
                organization_id=user.organization_id,
                actor_user_id=user.id,
                action=AuditAction.LOGIN,
                resource_type="user",
                resource_id=user.id,
                metadata_json={"email": email},
            )

            return user

    def issue_token(self, user: User) -> TokenResponse:
        """Create and return a signed JWT :class:`TokenResponse` for *user*.

        This is a synchronous, pure-domain operation — no DB access required.
        """
        token = create_access_token(
            subject=str(user.id),
            org_id=str(user.organization_id),
            role=user.role.value,
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
