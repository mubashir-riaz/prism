"""ModelPricing database model — stores per-model token pricing for cost calculation."""

from decimal import Decimal

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class ModelPricing(TimestampedBase):
    """Pricing record for a specific LLM model from a given provider.

    Stores the input and output token prices (in USD per 1,000 tokens) used by
    the cost calculation service to auto-fill ``cost_usd`` on ingested traces.

    The unique constraint on ``(provider, model)`` ensures each provider/model
    combination has exactly one active pricing row. Use an UPDATE (or the seed
    script's idempotent upsert) when prices change.

    Attributes:
        provider: LLM provider name, e.g. ``"openai"``, ``"anthropic"``.
        model: Model identifier as sent by callers, e.g. ``"gpt-4o-mini"``.
        input_price_per_1k: USD cost per 1,000 input (prompt) tokens.
        output_price_per_1k: USD cost per 1,000 output (completion) tokens.
    """

    __tablename__ = "model_pricing"
    __table_args__ = (
        # Enforce one pricing row per provider+model combination.
        UniqueConstraint("provider", "model", name="uq_model_pricing_provider_model"),
    )

    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    # Numeric(10, 6) — up to $9,999.999999 per 1K tokens; avoids float precision loss.
    input_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )
    output_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ModelPricing(provider='{self.provider}', model='{self.model}', "
            f"input={self.input_price_per_1k}, output={self.output_price_per_1k})>"
        )
