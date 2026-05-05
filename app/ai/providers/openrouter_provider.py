"""
OpenRouter LLM Provider — Uses OpenAI-compatible API via OpenRouter.
Last resort fallback when both Gemini and Groq are exhausted.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.ai.providers.resilience import ProviderCircuitBreaker, ProviderMetrics, retry_with_backoff
from app.core.config import settings
from app.core.exceptions import AITimeoutException, AITransientException

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    provider_name = "openrouter"

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        # Reuse HTTP client for connection pooling (longer timeout for free models)
        self._client = httpx.AsyncClient(
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_connections=settings.HTTP_MAX_CONNECTIONS, max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE),
        )
        # Resilience
        self.circuit = ProviderCircuitBreaker(
            "openrouter", 
            failure_threshold=settings.CIRCUIT_BREAKER_THRESHOLD, 
            cooldown_seconds=settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS
        )
        self.metrics = ProviderMetrics("openrouter")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate with retry + circuit breaker + metrics."""
        start = time.perf_counter()
        try:
            response = await retry_with_backoff(
                fn=lambda: self._single_attempt(request),
                max_retries=settings.LLM_MAX_RETRIES,
                base_delay=settings.LLM_RETRY_BASE_DELAY,
                provider_name=self.provider_name,
            )
            latency = (time.perf_counter() - start) * 1000
            self.circuit.record_success()
            self.metrics.record_success(latency)
            return response
        except Exception as exc:
            self.circuit.record_failure()
            self.metrics.record_failure(str(exc))
            raise

    async def _single_attempt(self, request: LLMRequest) -> LLMResponse:
        """Single generation attempt — called by retry_with_backoff."""
        model_name = request.model or settings.OPENROUTER_MODEL

        # Build messages in OpenAI format
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        messages.append({"role": "user", "content": request.user_input})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": settings.AI_TEMPERATURE,
            "max_tokens": settings.AI_MAX_TOKENS,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tegy-chatbot.com",
            "X-Title": settings.PROJECT_NAME,
        }

        try:
            resp = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

            if resp.status_code == 429:
                raise AITransientException("OpenRouter rate limit exceeded (429)")
            if resp.status_code >= 500:
                raise AITransientException(f"OpenRouter server error: {resp.status_code}")

            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            content = choice["message"].get("content", "")
            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                model=model_name,
                provider=self.provider_name,
                finish_reason=choice.get("finish_reason", "completed"),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )

        except httpx.TimeoutException as exc:
            raise AITimeoutException("OpenRouter request timed out") from exc
        except (AITransientException, AITimeoutException):
            raise
        except Exception as exc:
            logger.error("openrouter.generate.failed", exc_info=True)
            raise AITransientException(f"OpenRouter provider failed: {type(exc).__name__}") from exc

    async def count_tokens(self, content: str, model: str | None = None) -> int:
        """Estimate tokens (no dedicated counting endpoint)."""
        return max(1, int(len(content.split()) * 1.3))

    async def close(self) -> None:
        """Cleanup httpx client."""
        await self._client.aclose()
