"""Hashing utilities."""

import hashlib


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 digest of *data* as a lowercase hex string (64 chars).

    Parameters
    ----------
    data : bytes
        Arbitrary byte input.

    Returns
    -------
    str
        64-character lowercase hex string, e.g.
        ``"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"``
        for empty bytes.
    """
    return hashlib.sha256(data).hexdigest()
