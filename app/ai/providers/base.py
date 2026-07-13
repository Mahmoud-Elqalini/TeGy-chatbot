from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Union, Any

# Pre-compiled pattern for model channel markup (e.g. Command R+, gpt-oss on Fireworks).
# Format: <|channel|>analysis<|message|>...thinking...<|channel|>response<|message|>...reply...
_CHANNEL_TAG_RE = re.compile(r"<\|channel\|>.*?<\|message\|>", re.DOTALL)


def strip_channel_markup(content: str) -> str:
    """
    Strip leaked reasoning-channel markup from model output.

    Some open-weight models (Command R+, gpt-oss-120b) use a channel protocol
    like ``<|channel|>analysis<|message|>`` for internal reasoning and
    ``<|channel|>response<|message|>`` for the user-facing reply.  When the API
    doesn't strip these tokens, the raw markup leaks into the content field.

    Strategy:
      1. If a ``response`` channel exists → keep only the text after it.
      2. Otherwise → strip all channel/message tags and return what remains.
    """
    if "<|channel|>" not in content:
        return content

    # Prefer the explicit response channel
    response_marker = "<|channel|>response<|message|>"
    if response_marker in content:
        return content.split(response_marker)[-1].strip()

    # Fallback: remove all channel tags, keep the remaining text
    return _CHANNEL_TAG_RE.sub("", content).strip()


@dataclass(slots=True)
class LLMRequest:
    model: str
    system_prompt: str
    history: list[dict[str, Any]]
    user_input: str
    tools: list[dict[str, Any]] | None = None
    tool_choice: Optional[str] = None  # none, auto, required
    tool_results: list[dict[str, Any]] | None = None
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
    async def count_tokens(self, content: str, model: Optional[str] = None) -> int:
        raise NotImplementedError

    async def close(self) -> None:
        """Cleanup resources (httpx clients, etc.). Override if needed."""
        pass
