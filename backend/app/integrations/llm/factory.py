from functools import lru_cache

from app.core.config import settings
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.gemini_provider import GeminiProvider
from app.integrations.llm.openai_provider import OpenAIProvider


@lru_cache(maxsize=1)
def get_provider(name: str | None = None) -> LLMProvider:
    """
    Return a cached LLMProvider instance for the given provider name.

    ``@lru_cache(maxsize=1)`` ensures a single client is created per process,
    which is the SDK-recommended pattern — it avoids leaking HTTP connections.

    Supported names
    ---------------
    ``"openai"``  → :class:`~app.integrations.llm.openai_provider.OpenAIProvider`
    ``"gemini"``  → :class:`~app.integrations.llm.gemini_provider.GeminiProvider`

    Raises
    ------
    ValueError
        If *name* does not match any known provider.  Fail loud, fail fast;
        do not silently fall back to a default.
    """
    name = name or settings.LLM_PROVIDER
    if name == "openai":
        return OpenAIProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}")
