"""
Unit tests for GeminiProvider.

All tests use unittest.mock.AsyncMock — the real Gemini SDK is never called.
The mock mirrors the shape of a google.genai GenerateContentResponse.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.llm.gemini_provider import GeminiProvider
from app.integrations.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_response(
    text: str = "Hello!",
    prompt_token_count: int = 10,
    candidates_token_count: int = 5,
    total_token_count: int = 15,
) -> SimpleNamespace:
    """Build a SimpleNamespace shaped like a google.genai GenerateContentResponse.

    Fields used by GeminiProvider.complete():
        response.text
        response.usage_metadata.prompt_token_count
        response.usage_metadata.candidates_token_count
        response.usage_metadata.total_token_count
    """
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_token_count,
            candidates_token_count=candidates_token_count,
            total_token_count=total_token_count,
        ),
    )


def _make_provider(default_model: str = "gemini-2.0-flash") -> GeminiProvider:
    """Create a GeminiProvider with a dummy API key (no real network call)."""
    with patch("app.integrations.llm.gemini_provider.genai.Client"):
        provider = GeminiProvider(api_key="test-gemini-key", default_model=default_model)
    return provider


def _attach_mock_create(provider: GeminiProvider, fake_response) -> AsyncMock:
    """Replace provider._client.aio.models.generate_content with an AsyncMock."""
    mock = AsyncMock(return_value=fake_response)
    provider._client.aio = MagicMock()
    provider._client.aio.models = MagicMock()
    provider._client.aio.models.generate_content = mock
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_fields_map_correctly():
    """LLMResponse fields must map 1-to-1 from the Gemini response."""
    provider = _make_provider()
    fake = _make_fake_response(
        text="Bonjour!",
        prompt_token_count=8,
        candidates_token_count=3,
        total_token_count=11,
    )
    _attach_mock_create(provider, fake)

    result = await provider.complete("Say hello in French.")

    assert isinstance(result, LLMResponse)
    assert result.output == "Bonjour!"
    assert result.model == "gemini-2.0-flash"      # echoes resolved_model
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 3
    assert result.total_tokens == 11


@pytest.mark.asyncio
async def test_latency_ms_is_non_negative_int():
    """latency_ms must be a non-negative integer."""
    provider = _make_provider()
    _attach_mock_create(provider, _make_fake_response())

    result = await provider.complete("ping")

    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_model_kwarg_overrides_default():
    """Passing model= explicitly must override the provider's default_model."""
    provider = _make_provider(default_model="gemini-2.0-flash")
    fake = _make_fake_response()
    mock_create = _attach_mock_create(provider, fake)

    result = await provider.complete("hello", model="gemini-2.0-flash-lite")

    # SDK was called with the overridden model
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.0-flash-lite"

    # LLMResponse echoes resolved_model (Gemini doesn't echo in response body)
    assert result.model == "gemini-2.0-flash-lite"


@pytest.mark.asyncio
async def test_sdk_api_error_propagates():
    """If the SDK raises an exception the provider must NOT swallow it."""
    from google.genai import errors as genai_errors

    provider = _make_provider()
    mock_create = AsyncMock(
        side_effect=genai_errors.APIError("quota exceeded", response_json={})
    )
    provider._client.aio = MagicMock()
    provider._client.aio.models = MagicMock()
    provider._client.aio.models.generate_content = mock_create

    with pytest.raises(genai_errors.APIError):
        await provider.complete("trigger error")


@pytest.mark.asyncio
async def test_none_token_counts_default_to_zero():
    """If usage_metadata fields are None, provider must coerce them to 0."""
    provider = _make_provider()
    fake = _make_fake_response(
        prompt_token_count=None,
        candidates_token_count=None,
        total_token_count=None,
    )
    _attach_mock_create(provider, fake)

    result = await provider.complete("test")

    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert result.total_tokens == 0
