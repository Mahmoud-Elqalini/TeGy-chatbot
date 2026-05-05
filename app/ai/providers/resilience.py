"""
Lightweight resilience utilities for LLM providers.
Circuit breaker, retry with backoff, and in-memory observability counters.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, TypeVar

from app.core.exceptions import AITransientException, AITimeoutException

logger = logging.getLogger(__name__)
T = TypeVar("T")


# ── Circuit Breaker ───────────────────────────────────────────────────

class ProviderCircuitBreaker:
    """
    In-memory circuit breaker per provider.
    CLOSED → OPEN (after threshold failures) → HALF_OPEN (after cooldown) → CLOSED
    """

    def __init__(self, name: str, failure_threshold: int = 5, cooldown_seconds: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._state = "closed"
        self._last_failure_time: float = 0

    @property
    def state(self) -> str:
        # Auto-transition from OPEN → HALF_OPEN after cooldown
        if self._state == "open":
            if time.monotonic() - self._last_failure_time >= self.cooldown_seconds:
                self._state = "half_open"
        return self._state

    def is_available(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self._failure_count = 0
        if self._state != "closed":
            logger.info("circuit_breaker.recovered", extra={"provider": self.name})
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            prev = self._state
            self._state = "open"
            if prev != "open":
                logger.warning(
                    "circuit_breaker.opened",
                    extra={"provider": self.name, "failures": self._failure_count}
                )


# ── Metrics ───────────────────────────────────────────────────────────

class ProviderMetrics:
    """Simple in-memory counters for per-provider observability."""

    def __init__(self, name: str):
        self.name = name
        self.success_count = 0
        self.failure_count = 0
        self.timeout_count = 0
        self.rate_limit_count = 0
        self.fallback_count = 0
        self._total_latency_ms = 0.0

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self._total_latency_ms += latency_ms

    def record_failure(self, reason: str) -> None:
        self.failure_count += 1
        reason_lower = reason.lower()
        if "timeout" in reason_lower:
            self.timeout_count += 1
        if "rate" in reason_lower or "429" in reason:
            self.rate_limit_count += 1

    @property
    def avg_latency_ms(self) -> float:
        return self._total_latency_ms / max(self.success_count, 1)

    def summary(self) -> dict:
        return {
            "provider": self.name,
            "success": self.success_count,
            "failures": self.failure_count,
            "timeouts": self.timeout_count,
            "rate_limits": self.rate_limit_count,
            "fallbacks": self.fallback_count,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
        }


# ── Retry with Backoff ───────────────────────────────────────────────

async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 2,
    base_delay: float = 0.5,
    provider_name: str = "unknown",
) -> T:
    """
    Retry an async callable with exponential backoff.
    Retries ONLY on transient/timeout errors (not 4xx client errors).
    """
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except (AITransientException, AITimeoutException) as exc:
            if attempt == max_retries:
                raise  # Exhausted — let FallbackProvider handle it
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "provider.retry",
                extra={
                    "provider": provider_name,
                    "attempt": attempt + 1,
                    "delay_s": delay,
                    "error": str(exc),
                }
            )
            await asyncio.sleep(delay)

    raise AITransientException(f"{provider_name}: retries exhausted")  # Unreachable safeguard
