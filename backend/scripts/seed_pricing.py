"""Idempotent seed script for model pricing data.

Inserts known LLM model pricing into the ``model_pricing`` table.  Each row is
skipped when a matching (provider, model) pair already exists, so this script
is safe to re-run at any time without duplicating data.

Prices are in USD per 1,000 tokens (input / output).  Update the
``_PRICING_ROWS`` list when provider pricing changes.

Included models (prices as of late 2024 / early 2025):
  OpenAI
    gpt-4o              $0.0025 / $0.0100
    gpt-4o-mini         $0.00015 / $0.0006
    gpt-3.5-turbo       $0.0005 / $0.0015
  Anthropic
    claude-3-5-sonnet   $0.003 / $0.015
    claude-3-haiku      $0.00025 / $0.00125

Usage (from backend/ directory or container /app):
    python -m scripts.seed_pricing
or from repository root:
    python scripts/seed_pricing.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Ensure the backend directory is in sys.path when running as a script
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.model_pricing import ModelPricing


# ---------------------------------------------------------------------------
# Pricing table — (provider, model, input_per_1k, output_per_1k)
# ---------------------------------------------------------------------------

_PRICING_ROWS: list[tuple[str, str, str, str]] = [
    # provider,    model,                 input/1K,    output/1K
    ("openai",     "gpt-4o",              "0.0025",    "0.0100"),
    ("openai",     "gpt-4o-mini",         "0.00015",   "0.0006"),
    ("openai",     "gpt-3.5-turbo",       "0.0005",    "0.0015"),
    ("anthropic",  "claude-3-5-sonnet",   "0.003",     "0.015"),
    ("anthropic",  "claude-3-haiku",      "0.00025",   "0.00125"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


# ---------------------------------------------------------------------------
# Main seed coroutine
# ---------------------------------------------------------------------------


async def seed_pricing(session_factory=None) -> None:
    """Insert model pricing rows idempotently.

    For each (provider, model) pair, the row is skipped when it already exists.
    Existing prices are intentionally not updated — a separate migration or
    admin action should be used to change live pricing to avoid surprising
    cost re-calculations on historical traces.
    """
    factory = session_factory or async_session_factory

    print("\n==> Model pricing")

    async with factory() as session:
        inserted = 0
        skipped = 0

        for provider, model, input_price, output_price in _PRICING_ROWS:
            # Check for an existing row with the same (provider, model) key.
            result = await session.execute(
                select(ModelPricing).where(
                    ModelPricing.provider == provider,
                    ModelPricing.model == model,
                )
            )
            existing: ModelPricing | None = result.scalars().first()

            if existing is not None:
                _skip(
                    f"{provider}/{model} already exists "
                    f"(input={existing.input_price_per_1k}, "
                    f"output={existing.output_price_per_1k})"
                )
                skipped += 1
                continue

            session.add(
                ModelPricing(
                    provider=provider,
                    model=model,
                    input_price_per_1k=Decimal(input_price),
                    output_price_per_1k=Decimal(output_price),
                )
            )
            _ok(
                f"Inserted {provider}/{model} "
                f"(input=${input_price}/1K, output=${output_price}/1K)"
            )
            inserted += 1

        await session.commit()

    print(
        f"\nPricing seed complete — {inserted} inserted, {skipped} skipped.\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(seed_pricing())
