"""LLM service — high-level helper that calls the LLM and persists a trace."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm.base import LLMResponse
from app.integrations.llm.factory import get_provider
from app.schemas.trace import TraceIn
from app.services.trace_service import TraceService


class _SyntheticAPIKey:
    """Minimal stand-in that satisfies TraceService.create_trace's api_key contract.

    create_trace reads three FK attributes from the APIKey model:
        - api_key.project_id
        - api_key.environment_id
        - api_key.id

    By constructing this lightweight object from the caller-supplied IDs we
    re-use the existing service (and its cost-computation path) without
    requiring a live database row for the API key.
    """

    def __init__(
        self,
        project_id: uuid.UUID,
        environment_id: uuid.UUID,
        api_key_id: uuid.UUID,
    ) -> None:
        self.project_id = project_id
        self.environment_id = environment_id
        self.id = api_key_id


async def run_and_log(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    env_id: uuid.UUID,
    api_key_id: uuid.UUID,
    feature: str,
    prompt: str,
    model: str | None = None,
    prompt_version: str | None = None,
    metadata: dict[str, Any] | None = None,
    provider_name: str | None = None,
) -> LLMResponse:
    """Call the LLM and persist a trace through the standard trace_service path.

    This is the single internal entry-point for all Prism-initiated LLM calls.
    It wires together the provider, token/latency measurement, and trace
    persistence in one call — without going through the HTTP layer.

    Cost is intentionally NOT computed here.  ``TraceService.create_trace``
    already calls ``calculate_cost`` when ``cost_usd`` is ``None``, so there is
    exactly one source of truth for cost calculation.

    Exceptions from ``provider.complete()`` are intentionally **not** caught.
    If the LLM call fails, no trace is written and the exception propagates to
    the caller.  Phase 6 will add retry/error-row handling at a higher layer.

    Args:
        db:            Active async database session for trace persistence.
        org_id:        Organisation UUID (tenancy scope).
        project_id:    Project UUID — must exist in the database.
        env_id:        Environment UUID for the trace.
        api_key_id:    API key UUID attributed to the trace.
        feature:       Feature / call-site label (e.g. ``"summarise"``).
        prompt:        Full prompt text sent to the model.
        model:         Model override; falls back to the provider's default.
        prompt_version: Optional prompt version tag.
        metadata:      Arbitrary caller metadata stored in ``metadata_json``.
        provider_name: Provider override; falls back to ``settings.LLM_PROVIDER``.

    Returns:
        The :class:`~app.integrations.llm.base.LLMResponse` from the provider.

    Raises:
        Any exception raised by the underlying LLM provider (e.g.
        ``openai.APIConnectionError``) — callers decide how to handle failures.
    """
    provider = get_provider(provider_name)

    # --- LLM call — no try/except; failures bubble to the caller ---
    resp = await provider.complete(prompt, model=model)

    # --- Build TraceIn — cost_usd omitted so create_trace auto-computes it ---
    payload = TraceIn(
        feature=feature,
        model=resp.model,
        prompt=prompt,
        completion=resp.output,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        total_tokens=resp.total_tokens,
        latency_ms=resp.latency_ms,
        cost_usd=None,
        prompt_version=prompt_version,
        metadata_json=metadata or {},
    )

    # --- Persist via the same code path as POST /v1/traces ---
    synthetic_key = _SyntheticAPIKey(
        project_id=project_id,
        environment_id=env_id,
        api_key_id=api_key_id,
    )
    svc = TraceService(db)
    await svc.create_trace(api_key=synthetic_key, payload=payload)

    return resp
