"""
Performance Tracer — tracks elapsed time for each step in the chat pipeline.

Usage:
    tracer = PerformanceTracer()
    with tracer.step("resolve_context"):
        ...
    with tracer.step("load_memory"):
        ...
    tracer.log_summary(logger, request_id="abc-123")

The final log contains a breakdown like:
  ┌ resolve_context   :   45 ms
  ├ load_memory        :   12 ms
  ├ intent_detection   :    3 ms
  ├ ai_generation      :  820 ms
  ├ save_output        :   18 ms
  └ TOTAL              :  898 ms
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Span:
    name: str
    start: float
    end: float = 0.0

    @property
    def duration_ms(self) -> float:
        return round((self.end - self.start) * 1000, 2)


@dataclass
class PerformanceTracer:
    """Lightweight, zero-dependency tracer for synchronous / async code."""

    _spans: List[_Span] = field(default_factory=list)
    _start: float = field(default_factory=time.perf_counter)

    # ── public API ──────────────────────────────────────────────────────

    @contextmanager
    def step(self, name: str):
        """Context manager that records the duration of a named step."""
        span = _Span(name=name, start=time.perf_counter())
        try:
            yield span
        finally:
            span.end = time.perf_counter()
            self._spans.append(span)

    def mark(self, name: str, duration_ms: float) -> None:
        """Manually record a step that was already timed externally."""
        now = time.perf_counter()
        span = _Span(name=name, start=now - (duration_ms / 1000), end=now)
        self._spans.append(span)

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 2)

    def breakdown(self) -> Dict[str, float]:
        """Return an ordered dict of step_name → duration_ms."""
        return {s.name: s.duration_ms for s in self._spans}

    def summary_lines(self) -> List[str]:
        """Human-readable breakdown lines."""
        lines: List[str] = []
        for i, span in enumerate(self._spans):
            prefix = "┌" if i == 0 else "├"
            lines.append(f"  {prefix} {span.name:<28}: {span.duration_ms:>8.1f} ms")
        lines.append(f"  └ {'TOTAL':<28}: {self.total_ms:>8.1f} ms")
        return lines

    def log_summary(self, logger: Any, **extra: Any) -> None:
        """Emit one structured log entry with the full breakdown."""
        breakdown = self.breakdown()
        breakdown["__total_ms"] = self.total_ms

        # Structured log (works with both structlog and stdlib)
        if hasattr(logger, "bind"):
            # structlog
            logger.info(
                "perf.pipeline_breakdown",
                breakdown=breakdown,
                total_ms=self.total_ms,
                **extra,
            )
        else:
            # stdlib
            detail = " | ".join(f"{k}={v:.1f}ms" for k, v in breakdown.items())
            extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
            logger.info(f"perf.pipeline_breakdown | {detail} | {extra_str}")

    def as_dict(self) -> Dict[str, Any]:
        """Return the full trace as a serialisable dict."""
        return {
            "steps": self.breakdown(),
            "total_ms": self.total_ms,
        }
