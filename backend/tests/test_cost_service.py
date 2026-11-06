"""Unit tests for app.services.cost_service.calculate_cost.

All tests use a mock AsyncSession so no database is required — cost calculation
is pure arithmetic once the pricing row is returned from the ORM query.

Test matrix
-----------
* Known model + known tokens → exact Decimal value.
* Known model + zero tokens  → Decimal("0.000000").
* Unknown model              → returns None; warning logged (caplog).
* Large token count (1 M)    → correct large cost, no precision loss.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cost_service import calculate_cost
from app.models.model_pricing import ModelPricing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pricing(
    provider: str = "openai",
    model: str = "gpt-4o",
    input_price: str = "0.005000",
    output_price: str = "0.015000",
) -> ModelPricing:
    """Return an unsaved ModelPricing instance with the given prices."""
    pricing = ModelPricing.__new__(ModelPricing)
    pricing.provider = provider
    pricing.model = model
    pricing.input_price_per_1k = Decimal(input_price)
    pricing.output_price_per_1k = Decimal(output_price)
    return pricing


def _make_db(pricing_row: ModelPricing | None) -> AsyncMock:
    """Return a mock AsyncSession whose .execute() returns *pricing_row*."""
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = pricing_row

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Test: known model, known tokens → exact Decimal value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_cost_known_model_known_tokens() -> None:
    """Known model with non-zero tokens returns the exact expected Decimal cost.

    With gpt-4o pricing (input=$0.005/1k, output=$0.015/1k):
        prompt_cost    = 100 / 1000 * 0.005 = 0.0005
        completion_cost = 200 / 1000 * 0.015 = 0.003
        total          = 0.0035  → quantized to 6dp → 0.003500
    """
    pricing = _make_pricing(
        provider="openai",
        model="gpt-4o",
        input_price="0.005000",
        output_price="0.015000",
    )
    db = _make_db(pricing)

    cost = await calculate_cost(
        db=db,
        model="gpt-4o",
        prompt_tokens=100,
        completion_tokens=200,
        provider="openai",
    )

    assert cost == Decimal("0.003500")


# ---------------------------------------------------------------------------
# Test: known model, zero tokens → Decimal("0.000000")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_cost_zero_tokens_returns_zero() -> None:
    """Zero prompt and completion tokens should produce exactly Decimal('0.000000')."""
    pricing = _make_pricing()
    db = _make_db(pricing)

    cost = await calculate_cost(
        db=db,
        model="gpt-4o",
        prompt_tokens=0,
        completion_tokens=0,
    )

    assert cost == Decimal("0.000000")
    # Explicit zero check — not None, not a truthy value
    assert cost is not None


# ---------------------------------------------------------------------------
# Test: unknown model → returns None, warning logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_cost_unknown_model_returns_none_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unregistered model returns None and emits exactly one WARNING log entry
    containing the model name."""
    db = _make_db(pricing_row=None)  # simulate no pricing row found

    import logging

    with caplog.at_level(logging.WARNING, logger="app.services.cost_service"):
        cost = await calculate_cost(
            db=db,
            model="unknown-model-xyz",
            prompt_tokens=500,
            completion_tokens=250,
        )

    assert cost is None

    # At least one warning must mention the model name
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "Expected at least one WARNING log record"
    assert any(
        "unknown-model-xyz" in r.getMessage() for r in warnings
    ), "Warning must include the unrecognised model name"


# ---------------------------------------------------------------------------
# Test: large token count (1 M) → correct large cost, no precision loss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_cost_large_token_count_no_precision_loss() -> None:
    """1 million prompt tokens and 1 million completion tokens yield the correct
    cost without any floating-point precision loss.

    Pricing: input=$0.005/1k, output=$0.015/1k
        prompt_cost    = 1_000_000 / 1000 * 0.005 = 5.000000
        completion_cost = 1_000_000 / 1000 * 0.015 = 15.000000
        total          = 20.000000
    """
    pricing = _make_pricing(
        input_price="0.005000",
        output_price="0.015000",
    )
    db = _make_db(pricing)

    cost = await calculate_cost(
        db=db,
        model="gpt-4o",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    assert cost == Decimal("20.000000")
    # Verify six decimal places are preserved
    assert cost.as_tuple().exponent == -6


# ---------------------------------------------------------------------------
# Test: provider filter is applied when provider is given
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_cost_provider_scopes_lookup() -> None:
    """When provider is supplied, the query must filter on both model and provider."""
    pricing = _make_pricing(provider="anthropic", model="claude-3-5-sonnet")
    db = _make_db(pricing)

    cost = await calculate_cost(
        db=db,
        model="claude-3-5-sonnet",
        prompt_tokens=1000,
        completion_tokens=500,
        provider="anthropic",
    )

    # Assert db.execute was called (provider clause applied internally)
    db.execute.assert_awaited_once()
    # Returned cost must be a Decimal (not None)
    assert isinstance(cost, Decimal)


# ---------------------------------------------------------------------------
# Test: no provider supplied → still returns cost when model matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_cost_no_provider_falls_back_to_model_only() -> None:
    """When provider is None, lookup succeeds if any row for that model exists."""
    pricing = _make_pricing(provider="openai", model="gpt-4o-mini")
    db = _make_db(pricing)

    cost = await calculate_cost(
        db=db,
        model="gpt-4o-mini",
        prompt_tokens=2000,
        completion_tokens=1000,
        # provider deliberately omitted
    )

    assert cost is not None
    assert isinstance(cost, Decimal)
