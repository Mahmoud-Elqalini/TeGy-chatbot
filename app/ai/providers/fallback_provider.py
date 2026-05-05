"""
Fallback LLM Provider — Wraps multiple providers in priority order.

When the primary provider (Gemini) throws a rate limit or transient error,
this provider automatically tries the next one in the chain.

Chain: Gemini → Groq → OpenRouter

Resilience features:
- Skips providers with OPEN circuit breakers (no wasted latency)
- Logs per-provider metrics summary on each request
- Propagates close() to all sub-providers for graceful shutdown
"""
from __future__ import annotations

import logging
import time
from typing import List

from app.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.core.exceptions import AITransientException, AITimeoutException, LLMUnavailableException

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    """
    Cascading fallback provider with circuit breaker awareness.
    Tries each provider in order; skips those with open circuits.
    Only raises if ALL providers fail or are unavailable.
    """
    provider_name = "fallback"

    def __init__(self, providers: List[LLMProvider]):
        if not providers:
            raise ValueError("FallbackProvider requires at least one provider")
        self.providers = providers

    async def generate(self, request: LLMRequest) -> LLMResponse:
        last_exception: Exception | None = None
        skipped_count = 0

        for provider in self.providers:
            # Circuit breaker check — skip providers that are down
            circuit = getattr(provider, "circuit", None)
            if circuit and not circuit.is_available():
                logger.info(
                    "fallback.circuit_open_skipping",
                    extra={
                        "provider": provider.provider_name,
                        "circuit_state": circuit.state,
                    }
                )
                skipped_count += 1
                continue

            try:
                logger.info(
                    "fallback.trying",
                    extra={"provider": provider.provider_name}
                )

                # Each fallback provider uses its own default model
                fallback_request = LLMRequest(
                    model=None,
                    system_prompt=request.system_prompt,
                    history=request.history,
                    user_input=request.user_input,
                    metadata=request.metadata,
                )

                # For the primary (first) provider, keep the original model
                if provider == self.providers[0]:
                    fallback_request.model = request.model

                start = time.perf_counter()
                response = await provider.generate(fallback_request)
                latency_ms = (time.perf_counter() - start) * 1000

                if provider != self.providers[0]:
                    # Track fallback usage in metrics
                    metrics = getattr(provider, "metrics", None)
                    if metrics:
                        metrics.fallback_count += 1
                    logger.warning(
                        "fallback.used_backup",
                        extra={
                            "provider": provider.provider_name,
                            "original_provider": self.providers[0].provider_name,
                            "latency_ms": round(latency_ms, 2),
                        }
                    )

                return response

            except (AITransientException, AITimeoutException) as exc:
                logger.warning(
                    f"fallback.provider_failed: {provider.provider_name} | Error: {str(exc)}",
                    extra={
                        "provider": provider.provider_name,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
                last_exception = exc
                continue

            except Exception as exc:
                logger.error(
                    "fallback.unexpected_error",
                    extra={
                        "provider": provider.provider_name,
                        "error": str(exc),
                    }
                )
                last_exception = exc
                continue

        # All providers exhausted
        raise LLMUnavailableException(
            f"All {len(self.providers)} providers exhausted "
            f"({skipped_count} skipped by circuit breaker). "
            f"Last error: {last_exception}"
        )

    async def count_tokens(self, content: str, model: str | None = None) -> int:
        """Use the primary provider for token counting, fallback to estimation."""
        try:
            return await self.providers[0].count_tokens(content, model)
        except Exception:
            return max(1, int(len(content.split()) * 1.3))

    async def close(self) -> None:
        """Propagate close() to all sub-providers for graceful shutdown."""
        for provider in self.providers:
            try:
                await provider.close()
            except Exception as exc:
                logger.warning(f"Error closing {provider.provider_name}: {exc}")

    def get_metrics_summary(self) -> list[dict]:
        """Returns metrics from all providers that have them."""
        return [
            getattr(p, "metrics").summary()
            for p in self.providers
            if hasattr(p, "metrics")
        ]
