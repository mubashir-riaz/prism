"""Cost calculation service — derives USD cost from token counts and model pricing."""

from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.model_pricing import ModelPricing

logger = get_logger(__name__)

# Six decimal places matches Numeric(10, 6) on ModelPricing and Trace.cost_usd.
_QUANTIZE_EXP = Decimal("0.000001")


async def calculate_cost(
    db: AsyncSession,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider: str | None = None,
) -> Decimal | None:
    """Return the USD cost for a completed LLM call, or ``None`` when the model
    is not registered in the ``model_pricing`` table.

    The formula is::

        cost = (prompt_tokens / 1000 * input_price_per_1k)
             + (completion_tokens / 1000 * output_price_per_1k)

    Result is quantized to six decimal places (``ROUND_DOWN``) to stay within
    the ``Numeric(10, 6)`` column precision used for cost storage.

    Lookup strategy:
        - When *provider* is supplied, the query filters on both ``(provider,
          model)`` — matching the unique constraint on the table.
        - When *provider* is ``None``, the first ``model``-only match is used
          (useful for callers that don't track the provider).

    Args:
        db: Active async database session (read-only; no writes are made).
        model: Model identifier as recorded by the caller, e.g. ``"gpt-4o"``.
        prompt_tokens: Number of input / prompt tokens consumed.
        completion_tokens: Number of output / completion tokens produced.
        provider: Optional provider name (e.g. ``"openai"``). When given,
            restricts the lookup to that provider.

    Returns:
        A :class:`~decimal.Decimal` cost rounded to six decimal places, or
        ``None`` if no matching pricing row exists.
    """
    stmt = select(ModelPricing).where(ModelPricing.model == model)
    if provider is not None:
        stmt = stmt.where(ModelPricing.provider == provider)

    result = await db.execute(stmt)
    pricing: ModelPricing | None = result.scalars().first()

    if pricing is None:
        logger.warning(
            "Unknown model for cost calc: %s",
            model,
            provider=provider,
        )
        return None

    # Use Decimal arithmetic throughout to avoid any floating-point drift.
    prompt_cost = Decimal(prompt_tokens) / Decimal(1000) * pricing.input_price_per_1k
    completion_cost = (
        Decimal(completion_tokens) / Decimal(1000) * pricing.output_price_per_1k
    )
    total = (prompt_cost + completion_cost).quantize(_QUANTIZE_EXP, rounding=ROUND_DOWN)
    return total
