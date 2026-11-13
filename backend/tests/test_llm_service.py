"""
Unit tests for run_and_log.

Strategy
--------
* The LLM provider is replaced with an AsyncMock — the real OpenAI SDK is
  never called.
* Tests that touch the database use the ``db_session`` fixture from conftest
  (SQLite in-memory when Postgres is unavailable).
* The ``get_provider`` factory is patched via ``monkeypatch`` so the
  lru_cache does not carry state between tests.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_DOWN, Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.base import LLMResponse
from app.models.model_pricing import ModelPricing
from app.models.trace import Trace
from app.services.llm_service import run_and_log


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

PROMPT = "What is the capital of France?"
FEATURE = "geo-quiz"
PROMPT_TOKENS = 10
COMPLETION_TOKENS = 5
TOTAL_TOKENS = 15
LATENCY_MS = 123
MODEL = "gpt-4o-mini"
OUTPUT = "Paris."

FIXED_RESPONSE = LLMResponse(
    output=OUTPUT,
    model=MODEL,
    prompt_tokens=PROMPT_TOKENS,
    completion_tokens=COMPLETION_TOKENS,
    total_tokens=TOTAL_TOKENS,
    latency_ms=LATENCY_MS,
)

# Pricing used for cost assertion (matches seed_pricing.py values for gpt-4o-mini)
INPUT_PRICE_PER_1K = Decimal("0.000150")
OUTPUT_PRICE_PER_1K = Decimal("0.000600")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_provider(response: LLMResponse = FIXED_RESPONSE) -> MagicMock:
    """Return a mock provider whose complete() returns *response*."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    return provider


def _expected_cost(
    prompt_tokens: int,
    completion_tokens: int,
    input_price: Decimal = INPUT_PRICE_PER_1K,
    output_price: Decimal = OUTPUT_PRICE_PER_1K,
) -> Decimal:
    """Replicate the calculate_cost formula for assertion purposes."""
    quantize_exp = Decimal("0.000001")
    cost = (
        Decimal(prompt_tokens) / Decimal(1000) * input_price
        + Decimal(completion_tokens) / Decimal(1000) * output_price
    ).quantize(quantize_exp, rounding=ROUND_DOWN)
    return cost


async def _seed_pricing(db: AsyncSession) -> None:
    """Insert a gpt-4o-mini pricing row so cost auto-computation works."""
    pricing = ModelPricing(
        provider="openai",
        model=MODEL,
        input_price_per_1k=INPUT_PRICE_PER_1K,
        output_price_per_1k=OUTPUT_PRICE_PER_1K,
    )
    db.add(pricing)
    await db.flush()


async def _seed_project_and_key(db: AsyncSession, org_id: uuid.UUID):
    """Create the minimum DB rows needed for create_trace to succeed.

    Returns (project_id, env_id, api_key_id).
    """
    from app.models.enums import EnvironmentName
    from app.models.environment import Environment
    from app.models.project import Project

    project_id = uuid.uuid4()
    env_id = uuid.uuid4()
    api_key_id = uuid.uuid4()

    project = Project(
        id=project_id,
        organization_id=org_id,
        name="LLM Test Project",
        slug=f"llm-test-{project_id.hex[:8]}",
    )
    db.add(project)

    env = Environment(
        id=env_id,
        project_id=project_id,
        name=EnvironmentName.DEV,
    )
    db.add(env)

    await db.flush()
    return project_id, env_id, api_key_id


# ---------------------------------------------------------------------------
# Test 1 — provider.complete is called exactly once with the right prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_and_log_calls_provider_complete_once(
    db_session: AsyncSession,
    seeded_org,
):
    mock_provider = _make_mock_provider()
    project_id, env_id, api_key_id = await _seed_project_and_key(
        db_session, seeded_org.org_id
    )

    with patch(
        "app.services.llm_service.get_provider", return_value=mock_provider
    ):
        result = await run_and_log(
            db_session,
            org_id=seeded_org.org_id,
            project_id=project_id,
            env_id=env_id,
            api_key_id=api_key_id,
            feature=FEATURE,
            prompt=PROMPT,
            model=MODEL,
        )

    # complete() must have been called exactly once with the right prompt
    mock_provider.complete.assert_awaited_once_with(PROMPT, model=MODEL)

    # The returned value must be the provider's LLMResponse
    assert result is FIXED_RESPONSE


# ---------------------------------------------------------------------------
# Test 2 — a trace row is inserted with the correct fields + computed cost
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_and_log_inserts_trace_with_correct_fields(
    db_session: AsyncSession,
    seeded_org,
):
    await _seed_pricing(db_session)
    mock_provider = _make_mock_provider()
    project_id, env_id, api_key_id = await _seed_project_and_key(
        db_session, seeded_org.org_id
    )

    with patch(
        "app.services.llm_service.get_provider", return_value=mock_provider
    ):
        await run_and_log(
            db_session,
            org_id=seeded_org.org_id,
            project_id=project_id,
            env_id=env_id,
            api_key_id=api_key_id,
            feature=FEATURE,
            prompt=PROMPT,
            model=MODEL,
            prompt_version="v2",
            metadata={"source": "test"},
        )

    # Verify the trace was written to the DB
    result = await db_session.execute(
        select(Trace).where(Trace.project_id == project_id)
    )
    trace = result.scalars().first()

    assert trace is not None
    assert trace.feature == FEATURE
    assert trace.model == MODEL
    assert trace.prompt == PROMPT
    assert trace.completion == OUTPUT
    assert trace.prompt_tokens == PROMPT_TOKENS
    assert trace.completion_tokens == COMPLETION_TOKENS
    assert trace.total_tokens == TOTAL_TOKENS
    assert trace.latency_ms == LATENCY_MS
    assert trace.prompt_version == "v2"
    assert trace.metadata_json == {"source": "test"}

    # cost_usd must equal the Phase 1 formula result for gpt-4o-mini
    expected = _expected_cost(PROMPT_TOKENS, COMPLETION_TOKENS)
    assert trace.cost_usd == expected


# ---------------------------------------------------------------------------
# Test 3 — provider failure → no trace inserted, exception propagates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_and_log_propagates_provider_exception_without_inserting_trace(
    db_session: AsyncSession,
    seeded_org,
):
    import openai

    failing_provider = MagicMock()
    failing_provider.complete = AsyncMock(
        side_effect=openai.APIConnectionError(request=None)
    )
    project_id, env_id, api_key_id = await _seed_project_and_key(
        db_session, seeded_org.org_id
    )

    with patch(
        "app.services.llm_service.get_provider", return_value=failing_provider
    ):
        with pytest.raises(openai.APIConnectionError):
            await run_and_log(
                db_session,
                org_id=seeded_org.org_id,
                project_id=project_id,
                env_id=env_id,
                api_key_id=api_key_id,
                feature=FEATURE,
                prompt=PROMPT,
            )

    # No trace must have been written
    result = await db_session.execute(
        select(Trace).where(Trace.project_id == project_id)
    )
    assert result.scalars().first() is None
