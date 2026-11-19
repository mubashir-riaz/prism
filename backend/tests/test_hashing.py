"""
Unit tests for app/utils/hashing.py — sha256_hex.
"""

from app.utils.hashing import sha256_hex


# ---------------------------------------------------------------------------
# Correctness tests
# ---------------------------------------------------------------------------


def test_known_hash_of_empty_bytes():
    """SHA-256 of empty bytes is a well-known constant — the gold standard check."""
    expected = "e3b0c44298fc1c149afbf4c8996fb924" "27ae41e4649b934ca495991b7852b855"
    assert sha256_hex(b"") == expected


def test_known_hash_of_hello():
    """SHA-256('hello') is a widely published test vector."""
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e" "1b161e5c1fa7425e73043362938b9824"
    assert sha256_hex(b"hello") == expected


def test_same_bytes_produce_same_hash():
    """sha256_hex must be a pure deterministic function."""
    data = b'{"input": "q", "expected": "a"}'
    assert sha256_hex(data) == sha256_hex(data)


def test_different_bytes_produce_different_hashes():
    """Even a one-byte difference must yield a different hash."""
    assert sha256_hex(b"abc") != sha256_hex(b"abd")


def test_hash_is_64_character_lowercase_hex_string():
    """Output must always be exactly 64 hex characters, lowercase."""
    result = sha256_hex(b"prism dataset hashing")

    assert isinstance(result, str)
    assert len(result) == 64
    assert result == result.lower()
    assert all(c in "0123456789abcdef" for c in result)


def test_whitespace_difference_changes_hash():
    """Trailing whitespace must produce a different hash — content identity is strict."""
    assert sha256_hex(b"hello") != sha256_hex(b"hello ")


def test_large_payload_hashes_consistently():
    """sha256_hex must handle payloads larger than a single block (> 64 bytes)."""
    large = b'{"input": "question", "expected": "answer"}\n' * 1000
    h1 = sha256_hex(large)
    h2 = sha256_hex(large)

    assert h1 == h2
    assert len(h1) == 64
