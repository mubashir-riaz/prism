"""
Unit tests for OpenAIProvider.

All tests use unittest.mock.AsyncMock — the real OpenAI SDK is never called.
"""

import pytest
import openai
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.integrations.llm.openai_provider import OpenAIProvider
from app.integrations.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_response(
    content: str = "Hello!",
    model: str = "gpt-4o-mini",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    total_tokens: int = 15,
) -> SimpleNamespace:
    """Build a SimpleNamespace that mirrors the shape of an OpenAI chat response."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content)
            )
        ],
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )


def _make_provider(default_model: str = "gpt-4o-mini") -> OpenAIProvider:
    """Create an OpenAIProvider with a dummy API key (no real network call)."""
    return OpenAIProvider(api_key="test-key", default_model=default_model)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_fields_map_correctly():
    """LLMResponse fields must map 1-to-1 from the SDK response."""
    provider = _make_provider()
    fake = _make_fake_response(
        content="Paris",
        model="gpt-4o-mini",
        prompt_tokens=8,
        completion_tokens=3,
        total_tokens=11,
    )
    provider._client.chat.completions.create = AsyncMock(return_value=fake)

    result = await provider.complete("What is the capital of France?")

    assert isinstance(result, LLMResponse)
    assert result.output == "Paris"
    assert result.model == "gpt-4o-mini"
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 3
    assert result.total_tokens == 11


@pytest.mark.asyncio
async def test_latency_ms_is_non_negative_int():
    """latency_ms must be a non-negative integer."""
    provider = _make_provider()
    provider._client.chat.completions.create = AsyncMock(
        return_value=_make_fake_response()
    )

    result = await provider.complete("ping")

    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_model_kwarg_overrides_default():
    """Passing model= explicitly must win over the provider's default_model."""
    provider = _make_provider(default_model="gpt-4o-mini")
    fake = _make_fake_response(model="gpt-4o")
    mock_create = AsyncMock(return_value=fake)
    provider._client.chat.completions.create = mock_create

    result = await provider.complete("hello", model="gpt-4o")

    # SDK was called with the overridden model
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    # LLMResponse reflects what the SDK echoed back
    assert result.model == "gpt-4o"


@pytest.mark.asyncio
async def test_sdk_connection_error_propagates():
    """If the SDK raises APIConnectionError, the provider must NOT swallow it."""
    provider = _make_provider()
    provider._client.chat.completions.create = AsyncMock(
        side_effect=openai.APIConnectionError(request=None)
    )

    with pytest.raises(openai.APIConnectionError):
        await provider.complete("trigger error")
