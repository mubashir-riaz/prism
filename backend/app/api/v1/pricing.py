"""Model pricing read endpoint — GET /v1/pricing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.model_pricing import ModelPricing
from app.schemas.pricing import ModelPricingOut

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /v1/pricing — list all model pricing rows
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[ModelPricingOut],
    status_code=status.HTTP_200_OK,
    summary="List model pricing",
    description=(
        "Return every row in the model_pricing catalogue as a flat list ordered "
        "by provider then model name. No authentication required — this is "
        "read-only reference data."
    ),
)
async def list_pricing(
    db: AsyncSession = Depends(get_db),
) -> list[ModelPricingOut]:
    """Return all ModelPricing rows ordered by provider, then model."""
    result = await db.execute(
        select(ModelPricing).order_by(ModelPricing.provider, ModelPricing.model)
    )
    rows = result.scalars().all()
    return [ModelPricingOut.model_validate(row) for row in rows]


__all__ = ["router"]
