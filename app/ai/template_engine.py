"""
Template Engine — schema-driven tool-result renderer.

After tool execution, the Orchestrator calls ``TemplateEngine.match()`` with the
list of tool results.  If the first result's ``output`` dict matches a registered
schema pattern (all required fields present, optional condition satisfied), the
engine returns a ``TemplateResult`` containing the rendered response string.

The caller MUST fall through to the Renderer when this method returns ``None``.

Design constraints:
- Schema-driven: no tool-name assumptions, only output shape is inspected.
- Condition expressions are evaluated safely (no eval()).
- Immutable after construction: templates are registered at class definition.
- Fully typed.
- Thread-safe (no mutable state).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional

from app.core.observability import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SkipReason = Literal[
    "booking_created",
    "availability_true",
    "cancellation_success",
]


@dataclass(frozen=True, slots=True)
class TemplateResult:
    """Returned when a tool result matches a known schema pattern."""

    response: str
    skip_reason: SkipReason
    # Always zero — the Renderer LLM call was skipped entirely.
    saved_renderer_tokens: int


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TemplateSpec:
    """
    A single schema-driven template.

    Attributes:
        key:             Unique identifier (becomes ``skip_reason``).
        required_fields: All of these must be present and non-None in the output dict.
        condition:       Optional predicate called with the output dict; must return
                         True for the template to fire.  When None, no condition is
                         applied beyond field presence.
        template:        Format string.  ``{field}`` placeholders are filled from
                         the output dict.
    """

    key: SkipReason
    required_fields: tuple[str, ...]
    template: str
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None

    def render(self, output: Dict[str, Any]) -> str:
        """Fill template placeholders from the output dict."""
        return self.template.format(**{k: output[k] for k in self.required_fields})


# All templates registered here — extend this list to add new patterns.
_TEMPLATES: List[_TemplateSpec] = [
    # ── Booking Created ────────────────────────────────────────────────────
    _TemplateSpec(
        key="booking_created",
        required_fields=("booking_id",),
        template="تم الحجز بنجاح ✅\nرقم الحجز: {booking_id}",
    ),
    # ── Availability — ticket available ────────────────────────────────────
    _TemplateSpec(
        key="availability_true",
        required_fields=("available",),
        condition=lambda o: o.get("available") is True,
        template="التذاكر متاحة ✅",
    ),
    # ── Cancellation — booking cancelled ───────────────────────────────────
    _TemplateSpec(
        key="cancellation_success",
        required_fields=("cancelled",),
        condition=lambda o: o.get("cancelled") is True,
        template="تم إلغاء الحجز بنجاح ✅",
    ),
]

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_RENDERER_AVG_TOKENS: int = 600  # baseline when no real tracker is available


class TemplateEngine:
    """
    Inspects a list of tool results and attempts to match a registered template.

    Usage::

        engine = TemplateEngine()
        result = engine.match(tool_results)
        if result:
            # Skip Renderer — use result.response directly
        else:
            # Fall through to Renderer
    """

    def __init__(self, renderer_avg_tokens: int = _RENDERER_AVG_TOKENS) -> None:
        self._renderer_avg = renderer_avg_tokens

    def match(
        self, tool_results: List[Dict[str, Any]]
    ) -> Optional[TemplateResult]:
        """
        Try to match the first successful tool result against registered templates.

        Matching rules (all must hold for a template to fire):
          1. ``tool_results`` is a non-empty list.
          2. The first result has an ``"output"`` key whose value is a dict.
          3. All ``required_fields`` are present in the output and are not ``None``.
          4. The optional ``condition`` callable returns ``True``.

        Returns ``None`` on any mismatch — the caller must invoke the Renderer.

        Args:
            tool_results: The sanitised list produced by ``_execute_step()``.
        """
        t0 = time.perf_counter()

        if not tool_results:
            logger.debug("template_engine.skip: no_tool_results")
            return None

        # Inspect only the first result — multi-tool synthesis needs the Renderer.
        if len(tool_results) > 1:
            logger.debug(
                "template_engine.skip: multiple_tool_results",
                count=len(tool_results),
            )
            return None

        first = tool_results[0]
        output = first.get("output")

        if not isinstance(output, dict):
            logger.debug("template_engine.skip: output_not_dict", output_type=type(output).__name__)
            return None

        for spec in _TEMPLATES:
            # 1. Required fields must all be present and non-None
            if any(output.get(field) is None for field in spec.required_fields):
                continue

            # 2. Optional condition check
            if spec.condition is not None:
                try:
                    if not spec.condition(output):
                        continue
                except Exception as exc:
                    logger.warning(
                        "template_engine.condition_error",
                        template_key=spec.key,
                        error=str(exc),
                    )
                    continue

            # 3. Render response
            try:
                rendered = spec.render(output)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "template_engine.render_error",
                    template_key=spec.key,
                    error=str(exc),
                )
                continue

            elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
            logger.info(
                "template_engine.matched",
                skip_reason=spec.key,
                match_ms=elapsed_ms,
            )
            return TemplateResult(
                response=rendered,
                skip_reason=spec.key,
                saved_renderer_tokens=self._renderer_avg,
            )

        logger.debug("template_engine.no_match", output_keys=list(output.keys()))
        return None
