from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    output: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, prompt: str, *, model: str | None = None
    ) -> LLMResponse:
        ...
