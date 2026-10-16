"""
Prism security utilities — passwords, JWTs, and API keys.

Password hashing : Argon2id via argon2-cffi.
JWT              : PyJWT (HS256 by default, algorithm from settings).
API keys         : prism_<env>_<prefix12>_<secret32>, SHA-256 hashed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings
from app.exceptions import TokenError

# ---------------------------------------------------------------------------
# Internal Argon2id hasher (defaults: time=3, memory=65536, parallelism=4)
# ---------------------------------------------------------------------------
_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return an Argon2id hash of *plain*."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*, False on mismatch."""
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    """
    Return True if *hashed* was produced with outdated Argon2 parameters.
    Call this after a successful verify and re-hash if True.
    """
    return _ph.check_needs_rehash(hashed)


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------


def create_access_token(
    subject: str,
    org_id: str,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    """
    Create a signed JWT.

    Claims
    ------
    sub  : user id (string)
    org  : organisation id
    role : user's role within the org
    iat  : issued-at (UTC)
    exp  : expiry (UTC)
    """
    now = datetime.now(timezone.utc)
    ttl = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload: dict[str, Any] = {
        "sub": subject,
        "org": org_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ttl),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify *token*.

    Returns the claims dict on success.
    Raises :exc:`app.exceptions.TokenError` on invalid signature, expiry, or
    malformed input.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc
