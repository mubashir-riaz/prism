"""
Prism security utilities — passwords, JWTs, and API keys.

Password hashing : Argon2id via argon2-cffi.
JWT              : PyJWT (HS256 by default, algorithm from settings).
API keys         : prism_<env>_<prefix12>_<secret32>, SHA-256 hashed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import jwt

from app.core.config import settings

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


ALGORITHM = "HS256"


def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
