from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
from app.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.core.exceptions import AITimeoutException, AITransientException, LLMUnavailableException

import asyncio
from app.core.observability import get_logger

logger = get_logger(__name__)


class ResponseGenerator:
    """
    The ResponseGenerator handles the communication with the AI model.
    It includes retry logic to handle temporary failures from the AI provider.
    """

    def __init__(self, provider: LLMProvider):
        """
        Initializes the generator with a specific AI provider (like Gemini or FallbackProvider).
        
        Args:
            provider: The specific AI model provider to use.
        """
        self.provider = provider

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Sends a request to the AI model and returns its response.
        Resilience (retries and circuit breaking) is handled by the provider itself.
        """
        try:
            return await self.provider.generate(request)
        except (AITimeoutException, AITransientException) as exc:
            raise LLMUnavailableException(f"LLM provider unavailable: {exc}") from exc

    async def count_tokens(self, content: str, model: Optional[str] = None) -> int:
        """
        Calculates how many 'tokens' (pieces of words) are in a text string.
        This is important for tracking usage and costs.
        """
        return await self.provider.count_tokens(content, model)

    async def generate_simple(self, prompt: str) -> str:
        """
        A simplified version of 'generate' for quick, one-off questions.
        Useful for internal tasks like classifying text.
        """
        request = LLMRequest(
            model=None,
            system_prompt="You are a helpful assistant.",
            history=[],
            user_input=prompt
        )
        response = await self.generate(request)
        return response.content