import time

from openai import AsyncOpenAI

from app.core.config import settings
from app.integrations.llm.base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_API_KEY,
        )
        self._default_model = default_model or settings.LLM_DEFAULT_MODEL

    async def complete(
        self, prompt: str, *, model: str | None = None
    ) -> LLMResponse:
        resolved_model = model or self._default_model

        t0 = time.perf_counter()
        response = await self._client.chat.completions.create(
            model=resolved_model,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        return LLMResponse(
            output=response.choices[0].message.content,
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            latency_ms=latency_ms,
        )
