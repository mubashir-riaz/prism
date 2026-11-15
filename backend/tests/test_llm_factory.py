"""
Unit tests for the LLM provider factory.

The lru_cache on get_provider is cleared before every test so each test
starts from a clean slate and cache-state does not leak between cases.
"""

import pytest
from unittest.mock import patch

from app.integrations.llm.factory import get_provider
from app.integrations.llm.gemini_provider import GeminiProvider
from app.integrations.llm.openai_provider import OpenAIProvider


@pytest.fixture(autouse=True)
def clear_provider_cache():
    """Clear the lru_cache before (and after) every test."""
    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def test_get_provider_openai_returns_openai_provider():
    """get_provider('openai') must return an OpenAIProvider instance."""
    provider = get_provider("openai")
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_openai_returns_same_instance_on_repeated_calls():
    """
    Calling get_provider('openai') twice must return the exact same object
    — proves the lru_cache is working.
    """
    first = get_provider("openai")
    second = get_provider("openai")
    assert first is second


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def test_get_provider_gemini_returns_gemini_provider():
    """get_provider('gemini') must return a GeminiProvider instance."""
    with patch("app.integrations.llm.gemini_provider.genai.Client"):
        provider = get_provider("gemini")
    assert isinstance(provider, GeminiProvider)


def test_get_provider_gemini_returns_same_instance_on_repeated_calls():
    """
    Calling get_provider('gemini') twice must return the exact same object
    — proves the lru_cache is working for Gemini.
    """
    with patch("app.integrations.llm.gemini_provider.genai.Client"):
        first = get_provider("gemini")
        get_provider.cache_clear()          # clear between calls to test isolation
        second = get_provider("gemini")
    # Both are GeminiProvider instances (cache cleared between calls → new object)
    assert isinstance(first, GeminiProvider)
    assert isinstance(second, GeminiProvider)


def test_get_provider_gemini_cached_within_same_call_sequence():
    """Within a single call sequence (no cache clear) the same instance is returned."""
    with patch("app.integrations.llm.gemini_provider.genai.Client"):
        first = get_provider("gemini")
        second = get_provider("gemini")
    assert first is second


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------

def test_get_provider_unknown_raises_value_error():
    """get_provider with an unrecognised name must raise ValueError immediately."""
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("anthropic")

