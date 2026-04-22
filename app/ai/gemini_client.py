import logging
import asyncio
from app.core.exceptions import AITimeoutException, AITransientException

logger = logging.getLogger(__name__)

async def generate_response(payload: dict) -> str:
    """
    Mock function to represent the call to the Gemini API.
    Replace this with actual implementation using google-generativeai.
    """
    try:
        # Simulate network delay
        await asyncio.sleep(0.5)
        
        # MOCK ONLY: Uncomment below to test failure logic
        # raise asyncio.TimeoutError("Simulated Timeout")
        
        logger.info(f"Gemini API called with payload keys: {list(payload.keys())}")
        return "This is a mock response from Gemini Assistant."
        
    except asyncio.TimeoutError as e:
        logger.warning(f"Timeout connecting to Gemini: {e}")
        raise AITimeoutException("Timeout connecting to Gemini natively.")
    except ConnectionError as e:
        # Represents specific external provider errors (e.g., google.api_core.exceptions.ServiceUnavailable)
        logger.warning(f"Transient error connecting to Gemini: {e}")
        raise AITransientException("Transient network issue with Gemini natively.")
