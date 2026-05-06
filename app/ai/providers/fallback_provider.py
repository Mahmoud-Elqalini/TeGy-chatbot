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
        skipped_info = []

        # 1. Health-Based Selection: Rank providers by real-time health score
        # Providers with higher success rates and lower latency get priority.
        ranked_providers = sorted(
            self.providers,
            key=lambda p: (
                p.metrics.calculate_health_score(p.circuit) 
                if hasattr(p, "metrics") and hasattr(p, "circuit") 
                else 0.5
            ),
            reverse=True
        )

        for provider in ranked_providers:
            circuit = getattr(provider, "circuit", None)
            metrics = getattr(provider, "metrics", None)
            
            # 2. Hard Gate: Circuit Breaker Check with detailed logging
            if circuit and not circuit.is_available():
                reason = f"OPEN (Reason: {circuit.failure_reason}, Fails: {circuit.failure_count})"
                skipped_info.append(f"{provider.provider_name}: {reason}")
                continue

            # Check if health score is too low
            if metrics and circuit:
                score = metrics.calculate_health_score(circuit)
                if score < 0.2: # Hard floor for quality
                    skipped_info.append(f"{provider.provider_name}: Unhealthy (Score: {score})")
                    continue

            try:
                logger.info(
                    "fallback.trying", 
                    extra={
                        "provider": provider.provider_name,
                        "health_score": metrics.calculate_health_score(circuit) if metrics and circuit else "N/A"
                    }
                )

                fallback_request = LLMRequest(
                    model=None, # Default to provider's best model
                    system_prompt=request.system_prompt,
                    history=request.history,
                    user_input=request.user_input,
                    tools=request.tools,
                    tool_choice=request.tool_choice,
                    tool_results=request.tool_results,
                    metadata=request.metadata,
                )

                # Only pass the requested model if this provider is the 'Primary' for that model
                # or if it's the first attempt and the name matches.
                if provider == self.providers[0] and request.model:
                    fallback_request.model = request.model

                start = time.perf_counter()
                response = await provider.generate(fallback_request)
                latency_ms = (time.perf_counter() - start) * 1000

                # Log successful recovery or backup usage
                if provider != ranked_providers[0]:
                    logger.warning(
                        "fallback.used_alternative",
                        extra={
                            "provider": provider.provider_name,
                            "rank": ranked_providers.index(provider) + 1,
                            "latency_ms": round(latency_ms, 2),
                        }
                    )

                return response

            except (AITransientException, AITimeoutException) as exc:
                error_msg = str(exc)
                logger.warning(
                    f"fallback.provider_failed: {provider.provider_name} | Error: {error_msg}",
                    extra={
                        "provider": provider.provider_name,
                        "error": error_msg,
                        "error_type": type(exc).__name__,
                    }
                )
                last_exception = exc
                continue

            except Exception as exc:
                logger.error(
                    "fallback.unexpected_error",
                    extra={"provider": provider.provider_name, "error": str(exc)}
                )
                last_exception = exc
                continue

        # 3. Exhaustion: All health-checked options failed
        error_summary = " | ".join(skipped_info) if skipped_info else "None"
        raise LLMUnavailableException(
            f"All {len(self.providers)} providers exhausted. "
            f"Skipped status: {error_summary}. "
            f"Last technical error: {last_exception}"
        )

    async def count_tokens(self, content: str, model: str | None = None) -> int:
        try:
            return await self.providers[0].count_tokens(content, model)
        except Exception:
            return max(1, int(len(content.split()) * 1.3))

    async def close(self) -> None:
        for provider in self.providers:
            try:
                await provider.close()
            except Exception as exc:
                logger.warning(f"Error closing {provider.provider_name}: {exc}")

    def get_metrics_summary(self) -> list[dict]:
        return [
            getattr(p, "metrics").summary()
            for p in self.providers
            if hasattr(p, "metrics")
        ]
        