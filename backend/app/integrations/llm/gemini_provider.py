import time

from google import genai
from google.genai import types as genai_types

from app.core.config import settings
from app.integrations.llm.base import LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    """LLMProvider implementation backed by Google Gemini via the google-genai SDK.

    Uses ``google.genai.Client`` (async-capable) — the modern replacement for
    the legacy ``google.generativeai`` package.  A single client is created at
    construction time and reused across calls (SDK best practice).

    Token fields
    ------------
    The Gemini response exposes:
        - ``usage_metadata.prompt_token_count``   → prompt_tokens
        - ``usage_metadata.candidates_token_count`` → completion_tokens
        - ``usage_metadata.total_token_count``    → total_tokens

    Model echoing
    -------------
    The Gemini API does not echo the model name in the response body, so we
    echo back ``resolved_model`` ourselves — consistent with what OpenAIProvider
    does by reading ``response.model``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._client = genai.Client(
            api_key=api_key or settings.GEMINI_API_KEY,
        )
        self._default_model = default_model or settings.GEMINI_DEFAULT_MODEL

    async def complete(
        self, prompt: str, *, model: str | None = None
    ) -> LLMResponse:
        resolved_model = model or self._default_model

        t0 = time.perf_counter()
        response = await self._client.aio.models.generate_content(
            model=resolved_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        usage = response.usage_metadata
        return LLMResponse(
            output=response.text,
            model=resolved_model,
            prompt_tokens=usage.prompt_token_count or 0,
            completion_tokens=usage.candidates_token_count or 0,
            total_tokens=usage.total_token_count or 0,
            latency_ms=latency_ms,
        )
