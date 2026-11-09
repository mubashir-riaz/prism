"""Cursor encoding / decoding utilities for keyset pagination.

A cursor is an opaque, URL-safe base64 string that encodes a (created_at,
trace_id) pair.  It lets the list endpoint resume a result set from an exact
position without exposing raw SQL predicates to callers.

Wire format (before base64):
    {"ts": "<ISO-8601 datetime with timezone>", "id": "<UUID as hex string>"}
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from uuid import UUID


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class InvalidCursorError(Exception):
    """Raised when a cursor string cannot be decoded into a valid (datetime, UUID) pair.

    Internal parse errors (bad base64, bad JSON, missing keys, bad UUID, bad
    datetime) are caught and re-raised as this single type so callers never
    see implementation details leak through.
    """


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


def encode_cursor(created_at: datetime, trace_id: UUID) -> str:
    """Encode a (created_at, trace_id) pair into an opaque cursor string.

    Args:
        created_at: The ``created_at`` timestamp of the last-seen trace.
                    If the value is timezone-naive it is treated as UTC.
        trace_id:   The UUID of the last-seen trace.

    Returns:
        A URL-safe base64-encoded ASCII string suitable for use as a
        ``next_cursor`` / ``before`` query parameter.
    """
    # Normalise to an aware UTC datetime so round-trips are stable.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    payload = json.dumps(
        {"ts": created_at.isoformat(), "id": str(trace_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode("ascii")


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode an opaque cursor string back into a (datetime, UUID) pair.

    Args:
        cursor: The base64-encoded cursor produced by :func:`encode_cursor`.

    Returns:
        A ``(created_at, trace_id)`` tuple.

    Raises:
        InvalidCursorError: On *any* decoding failure — invalid base64,
            non-JSON payload, missing ``ts`` / ``id`` keys, unparseable
            datetime, or invalid UUID string.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
    except Exception:
        raise InvalidCursorError("Cursor is not valid base64.")

    try:
        data = json.loads(raw)
    except Exception:
        raise InvalidCursorError("Cursor payload is not valid JSON.")

    try:
        ts_raw = data["ts"]
    except (KeyError, TypeError):
        raise InvalidCursorError("Cursor is missing the 'ts' field.")

    try:
        id_raw = data["id"]
    except (KeyError, TypeError):
        raise InvalidCursorError("Cursor is missing the 'id' field.")

    try:
        created_at = datetime.fromisoformat(ts_raw)
    except Exception:
        raise InvalidCursorError(f"Cursor 'ts' value is not a valid ISO-8601 datetime: {ts_raw!r}")

    try:
        trace_id = UUID(id_raw)
    except Exception:
        raise InvalidCursorError(f"Cursor 'id' value is not a valid UUID: {id_raw!r}")

    return created_at, trace_id


__all__ = ["encode_cursor", "decode_cursor", "InvalidCursorError"]
