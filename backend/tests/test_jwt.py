"""Tests for JWT creation, claims validation, expiration, and tampering handling."""

import uuid

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.exceptions import TokenError


def test_create_access_token_produces_decodable_token_with_correct_claims() -> None:
    """create_access_token returns a valid JWT that decodes to the specified claims."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    role = "owner"

    token = create_access_token(
        subject=user_id,
        org_id=org_id,
        role=role,
        expires_minutes=30,
    )

    claims = decode_access_token(token)

    assert claims["sub"] == user_id
    assert claims["org"] == org_id
    assert claims["role"] == role
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] > claims["iat"]


def test_expired_token_raises_token_error() -> None:
    """A token whose expiration timestamp is in the past raises TokenError."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    # Create token expired 5 minutes ago
    expired_token = create_access_token(
        subject=user_id,
        org_id=org_id,
        role="admin",
        expires_minutes=-5,
    )

    with pytest.raises(TokenError, match="Token has expired"):
        decode_access_token(expired_token)


def test_tampered_token_payload_raises_token_error() -> None:
    """Tampering with the token payload invalidates the signature and raises TokenError."""
    token = create_access_token(
        subject=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        role="member",
    )

    parts = token.split(".")
    assert len(parts) == 3

    # Tamper with the payload part (middle part)
    tampered_payload = parts[1] + "tampered"
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

    with pytest.raises(TokenError, match="Token is invalid"):
        decode_access_token(tampered_token)


def test_tampered_token_signature_raises_token_error() -> None:
    """A token signed with a different secret key raises TokenError."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    # Manually encode with an attacker's key
    malicious_token = jwt.encode(
        {"sub": user_id, "org": org_id, "role": "admin"},
        "wrong-secret-key-that-does-not-match",
        algorithm="HS256",
    )

    with pytest.raises(TokenError, match="Token is invalid"):
        decode_access_token(malicious_token)


def test_malformed_token_string_raises_token_error() -> None:
    """Completely malformed strings raise TokenError."""
    with pytest.raises(TokenError, match="Token is invalid"):
        decode_access_token("not.a.valid.jwt.token")

    with pytest.raises(TokenError, match="Token is invalid"):
        decode_access_token("completely_random_gibberish")
