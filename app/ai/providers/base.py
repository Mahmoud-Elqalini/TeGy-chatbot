from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LLMRequest:
    model: str
    system_prompt: str
    history: list[dict[str, Any]]
    user_input: str
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    provider: str
    finish_reason: str = "completed"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: list[dict[str, Any]] | None = None
    raw: dict[str, Any] | None = None


class LLMProvider(ABC):
    provider_name: str

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def count_tokens(self, content: str, model: str | None = None) -> int:
        raise NotImplementedError
