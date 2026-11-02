"""Trace Pydantic schemas — ingestion input, full read-out, and slim creation receipt."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TraceIn(BaseModel):
    """Payload accepted by the trace ingestion endpoint.

    Enforces strict validation:
    - Token counts must be non-negative.
    - ``total_tokens`` is auto-computed as ``prompt_tokens + completion_tokens``
      when omitted; when provided it *must* equal that sum.
    - ``metadata_json`` is capped at 10 000 serialised bytes to prevent abuse.
    - ``extra = "forbid"`` rejects unknown fields so client typos are surfaced
      immediately rather than silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    # -------------------------------------------------------------------------
    # Correlation / feature metadata
    # -------------------------------------------------------------------------

    request_id: Optional[str] = Field(
        None,
        max_length=128,
        description="Client-supplied correlation ID for request tracing across services.",
    )
    feature: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Application feature / call-site that generated this trace.",
    )

    # -------------------------------------------------------------------------
    # LLM call data
    # -------------------------------------------------------------------------

    model: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="LLM model identifier (e.g. 'gpt-4o', 'claude-3-5-sonnet').",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="Full prompt text sent to the model.",
    )
    completion: str = Field(
        ...,
        min_length=0,
        max_length=100_000,
        description="Full completion text returned by the model.",
    )

    # -------------------------------------------------------------------------
    # Token accounting
    # -------------------------------------------------------------------------

    prompt_tokens: int = Field(
        0,
        ge=0,
        description="Number of tokens in the prompt.",
    )
    completion_tokens: int = Field(
        0,
        ge=0,
        description="Number of tokens in the completion.",
    )
    # None → auto-computed; provided → must equal prompt_tokens + completion_tokens.
    total_tokens: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Total token count. Auto-computed as prompt_tokens + completion_tokens "
            "when omitted. When provided, must equal that sum."
        ),
    )

    # -------------------------------------------------------------------------
    # Performance / cost
    # -------------------------------------------------------------------------

    latency_ms: Optional[int] = Field(
        None,
        ge=0,
        description="End-to-end latency of the LLM call in milliseconds.",
    )
    cost_usd: Optional[Decimal] = Field(
        None,
        ge=0,
        max_digits=12,
        decimal_places=6,
        description="Estimated cost of the call in USD (max 12 digits, 6 decimal places).",
    )

    # -------------------------------------------------------------------------
    # Prompt versioning (string for now; Phase 10 replaces with FK)
    # -------------------------------------------------------------------------

    prompt_version: Optional[str] = Field(
        None,
        max_length=64,
        description="Optional prompt version tag or identifier.",
    )

    # -------------------------------------------------------------------------
    # Arbitrary caller-supplied metadata
    # -------------------------------------------------------------------------

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary caller-supplied key/value metadata (max 10 000 serialised bytes).",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------

    @field_validator("metadata_json")
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Reject metadata payloads that exceed 10 000 serialised bytes."""
        serialised = json.dumps(v, separators=(",", ":"))
        if len(serialised) > 10_000:
            raise ValueError(
                f"metadata_json exceeds maximum serialised size of 10 000 bytes "
                f"(got {len(serialised)} bytes)."
            )
        return v

    @model_validator(mode="after")
    def validate_total_tokens(self) -> "TraceIn":
        """Auto-compute or cross-validate ``total_tokens``."""
        computed = self.prompt_tokens + self.completion_tokens
        if self.total_tokens is None:
            self.total_tokens = computed
        elif self.total_tokens != computed:
            raise ValueError(
                f"total_tokens ({self.total_tokens}) must equal "
                f"prompt_tokens + completion_tokens ({computed})."
            )
        return self


class TraceOut(BaseModel):
    """Full read representation of a Trace, returned by detail / list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    environment_id: uuid.UUID
    api_key_id: Optional[uuid.UUID]
    request_id: Optional[str]
    feature: str
    model: str
    prompt: str
    completion: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: Optional[int]
    cost_usd: Optional[Decimal]
    prompt_version: Optional[str]
    metadata_json: dict[str, Any]
    created_at: datetime


class TraceCreated(BaseModel):
    """Minimal receipt returned immediately after a successful trace ingestion.

    Intentionally omits the full payload to keep ingestion responses fast and
    to avoid echoing potentially large prompt/completion text back to the caller.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
