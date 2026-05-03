from __future__ import annotations
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

    def __init__(self, provider: LLMProvider, max_retries: int = 2):
        """
        Initializes the generator with a specific AI provider (like Gemini).
        
        Args:
            provider: The specific AI model provider to use.
            max_retries: How many times to try again if the AI fails temporarily.
        """
        self.provider = provider
        self.max_retries = max_retries

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Sends a request to the AI model and returns its response.
        If the model is busy or times out, it will retry based on `max_retries`.
        """
        attempts = 0
        while attempts <= self.max_retries:
            try:
                # Ask the provider to generate the response.
                return await self.provider.generate(request)
            except (AITimeoutException, AITransientException) as exc:
                # If a temporary error occurs, log it and try again after a short wait.
                attempts += 1
                logger.warning(
                    "response-generator.retry provider=%s attempt=%s error=%s",
                    self.provider.provider_name,
                    attempts,
                    exc,
                )
                if attempts <= self.max_retries:
                    # Wait longer with each retry (exponential backoff).
                    await asyncio.sleep(2 ** attempts)

        # If all retries fail, raise an error.
        raise LLMUnavailableException("LLM provider exhausted retries.")

    async def count_tokens(self, content: str, model: str | None = None) -> int:
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
