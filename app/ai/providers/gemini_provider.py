from __future__ import annotations

import asyncio

import google.generativeai as genai

from app.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.ai.safety import InputSafetyGuard
from app.core.config import settings
from app.core.exceptions import AITimeoutException, AITransientException
from app.core.observability import get_logger

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self, safety_guard: InputSafetyGuard | None = None):
        self.safety_guard = safety_guard or InputSafetyGuard()
        genai.configure(api_key=settings.GEMINI_API_KEY)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._generate_blocking, request),
                timeout=settings.GEMINI_READ_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise AITimeoutException("Timed out while waiting for Gemini response.") from exc
        except Exception as exc:
            error_name = type(exc).__name__
            if error_name in {"ResourceExhausted", "TooManyRequests", "ServiceUnavailable", "DeadlineExceeded"}:
                raise AITransientException(f"Gemini transient or rate limit error: {error_name}") from exc
            raise AITransientException(f"Gemini provider failed: {error_name}") from exc

    def _generate_blocking(self, request: LLMRequest) -> LLMResponse:
        model_name = request.model or settings.GEMINI_MODEL
        
        # Tools integration
        tools = None
        if request.metadata and "tools" in request.metadata:
            tools = request.metadata["tools"]

        model = genai.GenerativeModel(
            model_name=model_name,
            safety_settings=self.safety_guard.gemini_safety_settings(),
            generation_config={"temperature": 0.3},
            tools=tools
        )
        
        chat_history = []
        if request.system_prompt:
            chat_history.append({"role": "user", "parts": [request.system_prompt]})
            chat_history.append({"role": "model", "parts": ["Understood. I will follow the system instructions."]})
        for message in request.history:
            role = "model" if message.get("role") == "assistant" else "user"
            chat_history.append({"role": role, "parts": [message.get("content", "")]})

        chat = model.start_chat(history=chat_history)
        response = chat.send_message(request.user_input)
        
        # Extraction
        content = ""
        tool_calls = []
        
        if response.candidates:
            part = response.candidates[0].content.parts[0]
            if fn := getattr(part, "function_call", None):
                tool_calls.append({
                    "id": getattr(response, "id", "unknown"), # Gemini doesn't always have ID per call like OpenAI
                    "name": fn.name,
                    "arguments": dict(fn.args)
                })
            else:
                content = response.text

        # Extract usage metadata
        prompt_tokens = 0
        completion_tokens = 0
        if hasattr(response, "usage_metadata"):
            prompt_tokens = response.usage_metadata.prompt_token_count
            completion_tokens = response.usage_metadata.candidates_token_count

        return LLMResponse(
            content=content,
            model=model_name,
            provider=self.provider_name,
            finish_reason="completed",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=tool_calls if tool_calls else None,
            raw={"candidates": len(getattr(response, "candidates", []) or [])},
        )

    async def count_tokens(self, content: str, model: str | None = None) -> int:
        model_name = model or settings.GEMINI_MODEL
        try:
            m = genai.GenerativeModel(model_name=model_name)
            response = await asyncio.to_thread(m.count_tokens, content)
            return response.total_tokens
        except Exception as exc:
            logger.error("gemini.count_tokens.failed", error=exc)
            return 0
