"""Trace ingestion and debug retrieval endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_current_user
from app.db.session import get_db
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.trace import TraceCreated, TraceIn, TraceOut
from app.services.trace_service import TraceService

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /v1/traces — ingest a single LLM trace
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=TraceCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a trace",
    description=(
        "Ingest a single LLM trace. "
        "Authentication: X-API-Key header. "
        "Idempotency: not yet enforced — see Phase 5."
    ),
)
async def ingest_trace(
    payload: TraceIn,
    response: Response,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> TraceCreated:
    """Ingest a single LLM trace. Authentication: X-API-Key header. Idempotency: not yet enforced — see Phase 5."""
    service = TraceService(db)
    trace = await service.create_trace(api_key=api_key, payload=payload)

    # Set X-Request-ID to the client-supplied correlation ID when present,
    # falling back to the server-assigned trace UUID so callers can always
    # correlate the response to this specific trace.
    response.headers["X-Request-ID"] = (
        trace.request_id if trace.request_id else str(trace.id)
    )

    return TraceCreated.model_validate(trace)


# ---------------------------------------------------------------------------
# GET /v1/traces/{trace_id} — fetch a single trace (debug)
# ---------------------------------------------------------------------------


@router.get(
    "/{trace_id}",
    response_model=TraceOut,
    status_code=status.HTTP_200_OK,
    summary="Get a trace",
    description="Debug endpoint — full query API arrives in Phase 7.",
)
async def get_trace(
    trace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceOut:
    """Debug endpoint — full query API arrives in Phase 7."""
    service = TraceService(db)
    trace = await service.get_trace_for_user(trace_id=trace_id, user=current_user)
    return TraceOut.model_validate(trace)


__all__ = ["router"]
