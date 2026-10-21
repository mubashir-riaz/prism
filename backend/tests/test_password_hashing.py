"""Tests for password hashing and verification using Argon2id."""

import pytest
from argon2.exceptions import InvalidHashError

from app.core.security import hash_password, needs_rehash, verify_password


def test_hash_differs_across_calls_salted() -> None:
    """Argon2id produces unique salts, so hashing the same plaintext yields different hashes."""
    password = "SuperSecretPassword123!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    hash3 = hash_password(password)

    assert hash1 != hash2
    assert hash2 != hash3
    assert hash1 != hash3


def test_verify_password_accepts_correct() -> None:
    """verify_password returns True when given the correct plaintext password."""
    password = "CorrectHorseBatteryStaple42!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong() -> None:
    """verify_password returns False when given an incorrect plaintext password."""
    password = "ValidPassword123!"
    hashed = hash_password(password)

    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("validpassword123!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password("ValidPassword123! ", hashed) is False


def test_verify_password_handles_unicode_and_special_chars() -> None:
    """verify_password works reliably with unicode, emojis, and special characters."""
    password = "P@sswørd_🚀_测试_123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("P@sswørd_🚀_测试_123?", hashed) is False


def test_needs_rehash_for_current_parameters() -> None:
    """A fresh hash produced with current parameters should not need rehash."""
    hashed = hash_password("FreshPassword123!")
    assert needs_rehash(hashed) is False
