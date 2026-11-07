"""Tests for GET /v1/pricing endpoint.

Test matrix
-----------
* Empty table → 200 with an empty list [].
* 5 seeded rows → 200 with exactly 5 items; each item has the correct shape.
* Ordering → rows are returned ordered by provider, then model.
* No auth required → request without any credentials still returns 200.
"""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_pricing import ModelPricing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_ROWS: list[dict] = [
    {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
        "input_price_per_1k": Decimal("0.003000"),
        "output_price_per_1k": Decimal("0.015000"),
    },
    {
        "provider": "anthropic",
        "model": "claude-3-haiku",
        "input_price_per_1k": Decimal("0.000250"),
        "output_price_per_1k": Decimal("0.001250"),
    },
    {
        "provider": "google",
        "model": "gemini-1.5-pro",
        "input_price_per_1k": Decimal("0.003500"),
        "output_price_per_1k": Decimal("0.010500"),
    },
    {
        "provider": "openai",
        "model": "gpt-4o",
        "input_price_per_1k": Decimal("0.005000"),
        "output_price_per_1k": Decimal("0.015000"),
    },
    {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "input_price_per_1k": Decimal("0.000150"),
        "output_price_per_1k": Decimal("0.000600"),
    },
]


async def _seed_pricing_rows(
    session: AsyncSession,
    rows: list[dict],
) -> list[ModelPricing]:
    """Insert ModelPricing rows directly into the session and flush."""
    created: list[ModelPricing] = []
    for row in rows:
        pricing = ModelPricing(**row)
        session.add(pricing)
        created.append(pricing)
    await session.flush()
    return created


# ---------------------------------------------------------------------------
# GET /v1/pricing — empty table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pricing_empty_table_returns_empty_list(
    client: AsyncClient,
) -> None:
    """GET /v1/pricing with no rows in model_pricing returns 200 and an empty list."""
    response = await client.get("/v1/pricing")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /v1/pricing — no auth needed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pricing_requires_no_authentication(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /v1/pricing succeeds without any Authorization or X-API-Key header."""
    await _seed_pricing_rows(db_session, _SAMPLE_ROWS[:1])
    await db_session.commit()

    # Explicitly send no headers
    response = await client.get("/v1/pricing", headers={})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


# ---------------------------------------------------------------------------
# GET /v1/pricing — 5 seeded rows, correct shape and count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pricing_returns_all_seeded_rows(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /v1/pricing with 5 seeded rows returns 200 with exactly 5 items."""
    await _seed_pricing_rows(db_session, _SAMPLE_ROWS)
    await db_session.commit()

    response = await client.get("/v1/pricing")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


@pytest.mark.asyncio
async def test_list_pricing_items_have_correct_shape(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Every item in GET /v1/pricing has the four expected fields with correct types."""
    await _seed_pricing_rows(db_session, _SAMPLE_ROWS[:1])
    await db_session.commit()

    response = await client.get("/v1/pricing")
    assert response.status_code == 200
    item = response.json()[0]

    assert set(item.keys()) == {"provider", "model", "input_price_per_1k", "output_price_per_1k"}
    # Decimal fields are serialised as strings by Pydantic to preserve precision
    assert isinstance(item["provider"], str)
    assert isinstance(item["model"], str)
    # JSON numeric or string — either is valid; just assert parseable as Decimal
    Decimal(str(item["input_price_per_1k"]))
    Decimal(str(item["output_price_per_1k"]))


@pytest.mark.asyncio
async def test_list_pricing_values_match_seeded_data(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /v1/pricing values match what was inserted for a known row."""
    row = _SAMPLE_ROWS[3]  # openai / gpt-4o
    await _seed_pricing_rows(db_session, [row])
    await db_session.commit()

    response = await client.get("/v1/pricing")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert item["provider"] == "openai"
    assert item["model"] == "gpt-4o"
    assert Decimal(str(item["input_price_per_1k"])) == Decimal("0.005000")
    assert Decimal(str(item["output_price_per_1k"])) == Decimal("0.015000")


# ---------------------------------------------------------------------------
# GET /v1/pricing — ordering (provider ASC, model ASC)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pricing_ordered_by_provider_then_model(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /v1/pricing returns rows ordered by provider ASC, then model ASC."""
    # Insert in reverse order to prove ordering is applied server-side
    rows_reversed = list(reversed(_SAMPLE_ROWS))
    await _seed_pricing_rows(db_session, rows_reversed)
    await db_session.commit()

    response = await client.get("/v1/pricing")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5

    # Build the expected order: sorted by (provider, model)
    expected = sorted(
        _SAMPLE_ROWS,
        key=lambda r: (r["provider"], r["model"]),
    )
    for i, (item, exp) in enumerate(zip(data, expected)):
        assert item["provider"] == exp["provider"], f"Row {i} provider mismatch"
        assert item["model"] == exp["model"], f"Row {i} model mismatch"
