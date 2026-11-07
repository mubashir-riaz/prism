"""ModelPricing Pydantic read schema."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ModelPricingOut(BaseModel):
    """Read representation of a single ModelPricing row.

    Returned by ``GET /v1/pricing``. Decimal fields are serialised as strings
    by Pydantic to preserve full precision over JSON.
    """

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(..., description="LLM provider name, e.g. 'openai'.")
    model: str = Field(..., description="Model identifier, e.g. 'gpt-4o'.")
    input_price_per_1k: Decimal = Field(
        ...,
        description="USD cost per 1 000 input (prompt) tokens.",
    )
    output_price_per_1k: Decimal = Field(
        ...,
        description="USD cost per 1 000 output (completion) tokens.",
    )


__all__ = ["ModelPricingOut"]
