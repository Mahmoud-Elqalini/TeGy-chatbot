import logging
import asyncio
from typing import Optional
from app.ai.gemini_client import generate_response
from app.core.exceptions import AITimeoutException, AITransientException, LLMUnavailableException

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    async def get_response(self, payload: dict) -> str:
        """
        Attempts to get a response from the LLM via Gemini client.
        Implements async retry and graceful fallback mechanism.
        """
        attempts = 0
        while attempts <= self.max_retries:
            try:
                # LLM Call
                response = await generate_response(payload)
                return response
            except (AITimeoutException, AITransientException) as e:
                attempts += 1
                logger.error(f"LLM network issue (attempt {attempts}/{self.max_retries + 1}): {e}")
                if attempts <= self.max_retries:
                    await asyncio.sleep(2 ** attempts)
        
        logger.critical("LLM Service exhausted retries.")
        raise LLMUnavailableException()

