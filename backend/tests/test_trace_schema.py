"""Unit tests for TraceIn Pydantic schema validation."""

import json
from decimal import Decimal

import pytest

from app.schemas.trace import TraceIn


# ---------------------------------------------------------------------------
# Minimal valid payload factory
# ---------------------------------------------------------------------------


def _valid_payload(**overrides) -> dict:
    """Return a minimal valid TraceIn dict, with optional field overrides."""
    base = {
        "feature": "search",
        "model": "gpt-4o",
        "prompt": "Hello world",
        "completion": "Hi there",
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# total_tokens auto-computation
# ---------------------------------------------------------------------------


def test_total_tokens_auto_computed_when_omitted() -> None:
    """TraceIn auto-computes total_tokens = prompt_tokens + completion_tokens when omitted."""
    trace = TraceIn(**_valid_payload(prompt_tokens=7, completion_tokens=3))
    assert trace.total_tokens == 10


def test_total_tokens_accepted_when_correct() -> None:
    """TraceIn accepts total_tokens when it equals prompt_tokens + completion_tokens."""
    trace = TraceIn(**_valid_payload(prompt_tokens=4, completion_tokens=6, total_tokens=10))
    assert trace.total_tokens == 10


def test_total_tokens_zero_when_both_zero() -> None:
    """total_tokens is 0 when both prompt_tokens and completion_tokens are 0."""
    trace = TraceIn(**_valid_payload(prompt_tokens=0, completion_tokens=0))
    assert trace.total_tokens == 0


# ---------------------------------------------------------------------------
# total_tokens mismatch rejection
# ---------------------------------------------------------------------------


def test_total_tokens_mismatch_raises_value_error() -> None:
    """TraceIn raises ValueError when total_tokens ≠ prompt_tokens + completion_tokens."""
    with pytest.raises(ValueError, match="total_tokens"):
        TraceIn(**_valid_payload(prompt_tokens=5, completion_tokens=5, total_tokens=99))


# ---------------------------------------------------------------------------
# Negative field rejection
# ---------------------------------------------------------------------------


def test_negative_prompt_tokens_rejected() -> None:
    """TraceIn rejects negative prompt_tokens."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(prompt_tokens=-1))


def test_negative_completion_tokens_rejected() -> None:
    """TraceIn rejects negative completion_tokens."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(completion_tokens=-1))


def test_negative_latency_ms_rejected() -> None:
    """TraceIn rejects negative latency_ms."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(latency_ms=-1))


def test_negative_cost_usd_rejected() -> None:
    """TraceIn rejects negative cost_usd."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(cost_usd=Decimal("-0.000001")))


# ---------------------------------------------------------------------------
# metadata_json size cap
# ---------------------------------------------------------------------------


def test_metadata_json_under_limit_accepted() -> None:
    """metadata_json within 10 000 serialised bytes is accepted."""
    small_meta = {"key": "value"}
    trace = TraceIn(**_valid_payload(metadata_json=small_meta))
    assert trace.metadata_json == small_meta


def test_metadata_json_over_10kb_rejected() -> None:
    """TraceIn rejects metadata_json whose serialised size exceeds 10 000 bytes."""
    # Build a dict that serialises to >10 000 bytes
    big_meta = {"data": "x" * 10_001}
    with pytest.raises(ValueError, match="metadata_json exceeds"):
        TraceIn(**_valid_payload(metadata_json=big_meta))


def test_metadata_json_exactly_at_limit_accepted() -> None:
    """metadata_json at exactly 10 000 serialised bytes is accepted."""
    # Craft a payload whose JSON representation is exactly 10 000 bytes.
    # {"data":"xxx..."} — key+value overhead is len('{"data":""}') = 11 chars,
    # so we need 10000 - 11 = 9989 'x' characters.
    value = "x" * 9989
    meta = {"data": value}
    assert len(json.dumps(meta, separators=(",", ":"))) == 10_000
    trace = TraceIn(**_valid_payload(metadata_json=meta))
    assert trace.metadata_json["data"] == value


# ---------------------------------------------------------------------------
# extra="forbid" — unknown fields rejected
# ---------------------------------------------------------------------------


def test_unknown_field_rejected() -> None:
    """TraceIn rejects payloads containing unknown fields (extra='forbid')."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(organization_id="00000000-0000-0000-0000-000000000000"))


def test_project_id_field_rejected() -> None:
    """TraceIn rejects project_id — a common client mistake."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(project_id="00000000-0000-0000-0000-000000000000"))


def test_typo_field_rejected() -> None:
    """TraceIn rejects arbitrary typo fields like 'featrue' instead of 'feature'."""
    payload = _valid_payload()
    payload["featrue"] = "typo-value"  # deliberate typo
    with pytest.raises(ValueError):
        TraceIn(**payload)


# ---------------------------------------------------------------------------
# prompt / completion size limits
# ---------------------------------------------------------------------------


def test_prompt_exceeding_100kb_rejected() -> None:
    """TraceIn rejects prompts longer than 100 000 characters."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(prompt="x" * 100_001))


def test_prompt_at_100kb_accepted() -> None:
    """TraceIn accepts prompts of exactly 100 000 characters."""
    trace = TraceIn(**_valid_payload(prompt="x" * 100_000))
    assert len(trace.prompt) == 100_000


def test_completion_exceeding_100kb_rejected() -> None:
    """TraceIn rejects completions longer than 100 000 characters."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(completion="y" * 100_001))


def test_empty_completion_accepted() -> None:
    """TraceIn accepts an empty string completion (min_length=0)."""
    trace = TraceIn(**_valid_payload(completion=""))
    assert trace.completion == ""


def test_empty_prompt_rejected() -> None:
    """TraceIn rejects an empty string prompt (min_length=1)."""
    with pytest.raises(ValueError):
        TraceIn(**_valid_payload(prompt=""))


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


def test_optional_fields_default_to_none_or_empty() -> None:
    """Optional fields default correctly when omitted."""
    trace = TraceIn(**_valid_payload())
    assert trace.request_id is None
    assert trace.latency_ms is None
    assert trace.cost_usd is None
    assert trace.prompt_version is None
    assert trace.metadata_json == {}
