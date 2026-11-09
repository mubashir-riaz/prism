"""Tests for app/utils/cursor.py — encode_cursor / decode_cursor round-trips
and all InvalidCursorError edge-cases.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.utils.cursor import InvalidCursorError, decode_cursor, encode_cursor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_DT = datetime(2024, 6, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
_FIXED_UUID = UUID("12345678-1234-5678-1234-567812345678")


def _make_cursor(payload: dict) -> str:
    """Build a syntactically valid base64 cursor from a raw dict (may be semantically wrong)."""
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode("ascii")


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_basic_round_trip(self):
        cursor = encode_cursor(_FIXED_DT, _FIXED_UUID)
        result_dt, result_id = decode_cursor(cursor)

        assert result_dt == _FIXED_DT
        assert result_id == _FIXED_UUID

    def test_round_trip_with_random_uuid(self):
        uid = uuid4()
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        cursor = encode_cursor(dt, uid)
        got_dt, got_id = decode_cursor(cursor)

        assert got_dt == dt
        assert got_id == uid

    def test_timezone_naive_datetime_treated_as_utc(self):
        """A naive datetime should round-trip back as UTC-aware."""
        naive_dt = datetime(2024, 3, 10, 8, 0, 0)  # no tzinfo
        cursor = encode_cursor(naive_dt, _FIXED_UUID)
        got_dt, got_id = decode_cursor(cursor)

        expected = naive_dt.replace(tzinfo=timezone.utc)
        assert got_dt == expected
        assert got_id == _FIXED_UUID

    def test_cursor_is_ascii_string(self):
        cursor = encode_cursor(_FIXED_DT, _FIXED_UUID)
        assert isinstance(cursor, str)
        cursor.encode("ascii")  # must not raise

    def test_cursor_is_url_safe(self):
        """Base64 URL-safe alphabet — no '+' or '/' chars."""
        cursor = encode_cursor(_FIXED_DT, _FIXED_UUID)
        assert "+" not in cursor
        assert "/" not in cursor

    def test_deterministic_output(self):
        """Same inputs must always produce the same cursor."""
        c1 = encode_cursor(_FIXED_DT, _FIXED_UUID)
        c2 = encode_cursor(_FIXED_DT, _FIXED_UUID)
        assert c1 == c2


# ---------------------------------------------------------------------------
# InvalidCursorError — invalid base64
# ---------------------------------------------------------------------------


class TestInvalidBase64:
    def test_garbage_string(self):
        with pytest.raises(InvalidCursorError):
            decode_cursor("this is not base64!!!")

    def test_empty_string(self):
        with pytest.raises(InvalidCursorError):
            # Empty string decodes to empty bytes → invalid JSON
            decode_cursor("")

    def test_truncated_base64(self):
        cursor = encode_cursor(_FIXED_DT, _FIXED_UUID)
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor[:5] + "!!!!")


# ---------------------------------------------------------------------------
# InvalidCursorError — valid base64 but bad JSON
# ---------------------------------------------------------------------------


class TestInvalidJSON:
    def test_garbage_json(self):
        bad = base64.urlsafe_b64encode(b"not json at all").decode("ascii")
        with pytest.raises(InvalidCursorError):
            decode_cursor(bad)

    def test_partial_json(self):
        bad = base64.urlsafe_b64encode(b'{"ts": "2024-01-01"').decode("ascii")
        with pytest.raises(InvalidCursorError):
            decode_cursor(bad)

    def test_json_array_instead_of_object(self):
        bad = base64.urlsafe_b64encode(b'["ts", "id"]').decode("ascii")
        with pytest.raises(InvalidCursorError):
            decode_cursor(bad)


# ---------------------------------------------------------------------------
# InvalidCursorError — missing keys
# ---------------------------------------------------------------------------


class TestMissingKeys:
    def test_missing_id_key(self):
        cursor = _make_cursor({"ts": _FIXED_DT.isoformat()})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)

    def test_missing_ts_key(self):
        cursor = _make_cursor({"id": str(_FIXED_UUID)})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)

    def test_empty_object(self):
        cursor = _make_cursor({})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)


# ---------------------------------------------------------------------------
# InvalidCursorError — bad UUID string
# ---------------------------------------------------------------------------


class TestBadUUID:
    def test_uuid_is_plain_string(self):
        cursor = _make_cursor({"ts": _FIXED_DT.isoformat(), "id": "not-a-uuid"})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)

    def test_uuid_is_integer(self):
        cursor = _make_cursor({"ts": _FIXED_DT.isoformat(), "id": 12345})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)

    def test_uuid_is_null(self):
        cursor = _make_cursor({"ts": _FIXED_DT.isoformat(), "id": None})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)


# ---------------------------------------------------------------------------
# InvalidCursorError — bad datetime string
# ---------------------------------------------------------------------------


class TestBadDatetime:
    def test_ts_is_not_iso(self):
        cursor = _make_cursor({"ts": "15/06/2024 12:30", "id": str(_FIXED_UUID)})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)

    def test_ts_is_integer(self):
        cursor = _make_cursor({"ts": 1718454645, "id": str(_FIXED_UUID)})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)

    def test_ts_is_null(self):
        cursor = _make_cursor({"ts": None, "id": str(_FIXED_UUID)})
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor)
