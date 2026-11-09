"""Trace ingestion, query, and debug retrieval endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_current_user
from app.db.session import get_db
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.trace import TraceCreated, TraceIn, TraceListOut, TraceOut
from app.services.trace_service import TraceService
from app.utils.cursor import InvalidCursorError

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
# GET /v1/traces — cursor-paginated trace list
#
# IMPORTANT: this route MUST be declared before GET /{trace_id}.
# FastAPI evaluates routes in declaration order; if /{trace_id} came first,
# the literal path "/v1/traces" would be matched with trace_id="" and FastAPI
# would return 422 "trace_id is not a valid UUID" before reaching this handler.
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=TraceListOut,
    status_code=status.HTTP_200_OK,
    summary="List traces",
    description=(
        "Return a cursor-paginated list of traces scoped to the authenticated "
        "API key's organisation.  Supports filtering by model, feature, and "
        "time range.  Pass ``cursor`` from a previous response's ``next_cursor`` "
        "to retrieve the following page."
    ),
)
async def list_traces(
    model: str | None = Query(None, description="Filter by exact model name."),
    feature: str | None = Query(None, description="Filter by exact feature name."),
    since: datetime | None = Query(None, description="Inclusive lower bound on created_at (ISO-8601)."),
    until: datetime | None = Query(None, description="Inclusive upper bound on created_at (ISO-8601)."),
    cursor: str | None = Query(None, description="Opaque pagination cursor from a previous response."),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of traces to return (1-200)."),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
) -> TraceListOut:
    """Return a cursor-paginated list of traces for the authenticated organisation."""
    # org_id is derived from the authenticated API key's project — never from
    # the query string — so tenants cannot read each other's traces.
    org_id: uuid.UUID = api_key.project.organization_id

    service = TraceService(db)
    try:
        return await service.list_traces(
            db,
            org_id=org_id,
            model=model,
            feature=feature,
            since=since,
            until=until,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError:
        raise HTTPException(status_code=400, detail="Invalid cursor.")


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
