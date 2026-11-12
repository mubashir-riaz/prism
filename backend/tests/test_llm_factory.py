"""
Unit tests for the LLM provider factory.

The lru_cache on get_provider is cleared before every test so each test
starts from a clean slate and cache-state does not leak between cases.
"""

import pytest

from app.integrations.llm.factory import get_provider
from app.integrations.llm.openai_provider import OpenAIProvider


@pytest.fixture(autouse=True)
def clear_provider_cache():
    """Clear the lru_cache before (and after) every test."""
    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_provider_openai_returns_openai_provider():
    """get_provider('openai') must return an OpenAIProvider instance."""
    provider = get_provider("openai")
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_unknown_raises_value_error():
    """get_provider with an unrecognised name must raise ValueError immediately."""
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("anthropic")


def test_get_provider_returns_same_instance_on_repeated_calls():
    """
    Calling get_provider() twice with the same argument must return the
    exact same object — proves the lru_cache is working.
    """
    first = get_provider("openai")
    second = get_provider("openai")
    assert first is second
