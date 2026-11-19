"""
Unit tests for app/utils/jsonl.py — parse_jsonl and InvalidJSONLError.
"""

import pytest

from app.utils.jsonl import InvalidJSONLError, parse_jsonl


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_valid_three_line_file_returns_three_dicts():
    """A clean 3-line JSONL file must return exactly 3 dicts in order."""
    data = (
        b'{"input": "q1", "expected": "a1"}\n'
        b'{"input": "q2", "expected": "a2"}\n'
        b'{"input": "q3", "expected": "a3"}\n'
    )
    result = parse_jsonl(data)

    assert len(result) == 3
    assert result[0] == {"input": "q1", "expected": "a1"}
    assert result[1] == {"input": "q2", "expected": "a2"}
    assert result[2] == {"input": "q3", "expected": "a3"}


def test_empty_bytes_returns_empty_list():
    """Empty input must return an empty list, not raise."""
    assert parse_jsonl(b"") == []


def test_only_blank_lines_returns_empty_list():
    """A file containing only blank lines must return an empty list."""
    data = b"\n\n\n"
    assert parse_jsonl(data) == []


def test_lines_with_trailing_whitespace_are_parsed_correctly():
    """Leading/trailing whitespace around a valid JSON line must be ignored."""
    data = b'   {"input": "q", "expected": "a"}   \n'
    result = parse_jsonl(data)

    assert result == [{"input": "q", "expected": "a"}]


def test_mixed_blank_and_data_lines():
    """Blank lines interspersed between data lines must be skipped."""
    data = (
        b'{"input": "q1", "expected": "a1"}\n'
        b"\n"
        b'{"input": "q2", "expected": "a2"}\n'
        b"\n"
    )
    result = parse_jsonl(data)

    assert len(result) == 2
    assert result[0]["input"] == "q1"
    assert result[1]["input"] == "q2"


def test_crlf_line_endings_work_the_same_as_lf():
    """Windows CRLF line endings must be handled identically to LF."""
    lf_data = (
        b'{"input": "q1", "expected": "a1"}\n'
        b'{"input": "q2", "expected": "a2"}\n'
    )
    crlf_data = (
        b'{"input": "q1", "expected": "a1"}\r\n'
        b'{"input": "q2", "expected": "a2"}\r\n'
    )

    assert parse_jsonl(lf_data) == parse_jsonl(crlf_data)


def test_rows_with_optional_metadata_field_are_returned_as_is():
    """Rows with extra fields (e.g. metadata) pass through without modification."""
    data = b'{"input": "q", "expected": "a", "metadata": {"tag": "v1"}}\n'
    result = parse_jsonl(data)

    assert result[0]["metadata"] == {"tag": "v1"}


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


def test_invalid_json_on_line_2_raises_invalid_jsonl_error():
    """A bad JSON line must raise InvalidJSONLError with the correct line number."""
    data = (
        b'{"input": "q1", "expected": "a1"}\n'
        b"this is not json\n"
        b'{"input": "q3", "expected": "a3"}\n'
    )
    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(data)

    assert exc_info.value.line_number == 2
    assert exc_info.value.reason  # non-empty reason string


def test_invalid_json_error_carries_human_readable_reason():
    """The reason string must be non-empty and contain useful information."""
    data = b'{"ok": true}\n{bad json\n'

    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(data)

    err = exc_info.value
    assert err.line_number == 2
    assert len(err.reason) > 0


def test_invalid_utf8_raises_invalid_jsonl_error():
    """Non-UTF-8 bytes must raise InvalidJSONLError with a clear message."""
    invalid_utf8 = b"\xff\xfe{}"

    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(invalid_utf8)

    err = exc_info.value
    assert "UTF-8" in err.reason or "utf" in err.reason.lower()


def test_json_array_on_a_line_raises_invalid_jsonl_error():
    """A line that is a JSON array (not an object) must raise InvalidJSONLError."""
    data = b'["not", "an", "object"]\n'

    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(data)

    err = exc_info.value
    assert err.line_number == 1
    assert "object" in err.reason.lower() or "dict" in err.reason.lower()


def test_json_scalar_on_a_line_raises_invalid_jsonl_error():
    """A line that is a bare JSON scalar must raise InvalidJSONLError."""
    data = b'{"ok": true}\n42\n'

    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(data)

    err = exc_info.value
    assert err.line_number == 2


def test_error_message_includes_line_number():
    """str(exc) must include the 1-indexed line number for editor usability."""
    data = b'{"ok": 1}\nbad\n'

    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(data)

    assert "2" in str(exc_info.value)


def test_error_on_first_line():
    """An error on line 1 must report line_number == 1, not 0."""
    data = b"not json at all\n"

    with pytest.raises(InvalidJSONLError) as exc_info:
        parse_jsonl(data)

    assert exc_info.value.line_number == 1
