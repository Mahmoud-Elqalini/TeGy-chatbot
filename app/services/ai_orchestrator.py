from __future__ import annotations
from app.core.config import settings

import time
import copy
from datetime import datetime
from typing import Optional, Union, Any, List, Dict

from app.ai.fast_path_router import FastPathRouter
from app.ai.providers.base import LLMRequest, LLMResponse
from app.ai.prompt_loader import PromptLoader
from app.ai.response_generator import ResponseGenerator
from app.ai.safety import ResponseValidator
from app.ai.template_engine import TemplateEngine
from app.ai.tool_registry import ToolRegistry
from app.core.observability import get_logger, set_trace_id, set_trace_layer, reset_trace_layer, trace_layer_ctx
from app.core.trace_context import RequestTrace, set_active_trace, reset_active_trace, get_active_trace
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class OrchestratorRuntimeDeps:
    db: AsyncSession
    main_db: AsyncSession

    def to_dict(self) -> dict:
        return {"db": self.db, "main_db": self.main_db}


logger = get_logger(__name__)

INTENT_TOOL_MAP = {
    "support_event":     "search_events",
    "get_event_details": "get_event_details",
    "create_booking":    "create_booking",
    "get_booking":       "get_booking",
    "cancel_booking":    "cancel_booking",
    "get_user_bookings": "get_user_bookings",
}


class AIOrchestrator:

    def __init__(
        self,
        response_generator: ResponseGenerator,
        response_validator: ResponseValidator,
        tool_registry: Optional[ToolRegistry] = None,
        runtime_deps: Optional[OrchestratorRuntimeDeps] = None,
        fast_path_router: Optional[FastPathRouter] = None,
        template_engine: Optional[TemplateEngine] = None,
    ):
        self.response_generator = response_generator
        self.response_validator = response_validator
        self.tool_registry = tool_registry
        self.runtime_deps = runtime_deps
        # Optimisation layers — defaulted so existing callers need no changes
        self.fast_path_router: FastPathRouter = fast_path_router or FastPathRouter()
        self.template_engine: TemplateEngine = template_engine or TemplateEngine()

    def _is_valid_tool_call(self, tool_calls: Optional[List], expected_tool: str) -> bool:
        if not tool_calls or not isinstance(tool_calls, list):
            return False
        return any(
            isinstance(call, dict) and call.get("name") == expected_tool
            for call in tool_calls
        )

    def _attach_tools(self, request: LLMRequest) -> LLMRequest:
        """Attach tools for reasoning phase. Synthesis detected via tool_results."""
        is_synthesis = bool(request.tool_results)
        if is_synthesis:
            request.tools = None
            request.tool_choice = "none"
        elif self.tool_registry:
            all_tools = self.tool_registry.get_tool_definitions()
            intent = request.metadata.get("intent") if request.metadata else None
            
            # Dynamic Tool Injection based on intent
            if intent in ["booking", "create_booking"]:
                allowed = {"search_events", "get_event_details", "check_availability", "get_user_profile"}
            elif intent in ["discover", "support_event", "get_event_details", "search_events"]:
                allowed = {"search_events", "get_event_details", "get_user_profile", "report_support_issue"}
            elif intent in ["manage_booking", "get_booking", "cancel_booking", "get_user_bookings"]:
                allowed = {"get_booking", "cancel_booking", "get_user_bookings", "get_user_profile"}
            elif intent in ["support_technical", "support_billing", "support_general"]:
                allowed = {"report_support_issue", "get_user_profile"}
            elif intent in ["greeting", "general_faq", "chit_chat", "fallback"]:
                allowed = {"get_user_profile"}
            else:
                allowed = None  # Allow all if unknown intent
                
            if allowed is not None:
                request.tools = [t for t in all_tools if t["name"] in allowed]
            else:
                request.tools = all_tools
                
        return request

    async def generate_response(
        self,
        request: LLMRequest,
        session_id: Optional[int] = None,
    ) -> LLMResponse:
        start_time = time.perf_counter()

        self._attach_tools(request)

        # Hard gate — synthesis must never have tools
        if request.tool_results and request.tools is not None:
            logger.critical("security.blind_synthesis_violation", session_id=session_id)
            raise RuntimeError("Tools leaked into synthesis context.")

        try:
            response = await self.response_generator.generate(request)
            latency = time.perf_counter() - start_time

            logger.info(
                "ai.generation.completed",
                session_id=session_id,
                latency_ms=round(latency * 1000, 2),
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                finish_reason=response.finish_reason,
                has_tool_calls=bool(response.tool_calls),
            )

            if not response.tool_calls:
                response.content = self.response_validator.validate_response(response.content)

            return response

        except Exception as exc:
            latency = time.perf_counter() - start_time
            logger.error(
                "ai.generation.failed",
                session_id=session_id,
                latency_ms=round(latency * 1000, 2),
                error=str(exc),
            )
            raise

    async def handle_tool_calls(
        self, 
        response: LLMResponse, 
        session_id: Any = None, 
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not response.tool_calls or not self.tool_registry:
            return []

        results = []
        tool_deps = self.runtime_deps.to_dict() if self.runtime_deps else {}
        if session_id:
            tool_deps["session_id"] = session_id
        if user_id:
            tool_deps["user_id"] = user_id

        for call in response.tool_calls:
            name = call.get("name")
            args = call.get("arguments") or {}
            call_id = call.get("id")

            try:
                logger.info("tool.execution_started", tool_name=name, call_id=call_id)
                start_tool = time.perf_counter()
                result = await self.tool_registry.call_tool(
                    name, runtime_deps=tool_deps, **args
                )
                tool_time = round((time.perf_counter() - start_tool) * 1000, 2)
                
                trace = get_active_trace()
                if trace:
                    layer = trace_layer_ctx.get()
                    if layer in trace.layers:
                        trace.layers[layer].tool_ms += tool_time

                if isinstance(result, str):
                    result = self.response_validator.sanitize_tool_output(result)
                elif isinstance(result, (dict, list)):
                    result_str = str(result)
                    if "[REDACTED" in self.response_validator.sanitize_tool_output(result_str):
                        result = "[REDACTED: Suspicious content detected in tool output]"

                logger.info("tool.execution_completed", tool_name=name, call_id=call_id, status="success")
                results.append({"tool_call_id": call_id, "tool_name": name, "output": result})

            except Exception as exc:
                logger.error("tool.call.failed", tool=name, error=str(exc))
                results.append({"tool_call_id": call_id, "tool_name": name, "error": str(exc)})

        return results

    async def generate_complex(
        self,
        user_input: str,
        intent: str,
        payload: dict,
        session_id: Any,
        route: str = "llm_path",
    ) -> tuple[str, int, list[dict], dict[str, int]]:
        """
        Dispatch entry point.

        Routing logic:
          1. If route == "fast_path", try FastPathRouter first.
             - On match  → return immediately, zero LLM calls.
             - On miss   → fall through to _execute_llm_path().
             (Fixes the pre-existing bug where booking → fast_path incorrectly
             hit a barebones LLM call with no tools or system prompt.)
          2. Everything else → _execute_llm_path().
        """
        if route == "fast_path":
            # NOTE: This is now a SECONDARY SAFETY FALLBACK check.
            # The PRIMARY zero-context fast path check happens upstream in ChatApplicationService.execute().
            # This remains here to catch any internal reroutes or direct Orchestrator calls.
            fp_result = self.fast_path_router.match(user_input)
            if fp_result is not None:
                # ── Build a minimal trace so logs are consistent ──────────
                trace_id = set_trace_id()
                trace = RequestTrace(
                    trace_id=trace_id,
                    fast_path_used=True,
                    fast_path_type=fp_result.fast_path_type,
                    planner_skipped=True,
                    renderer_skipped=True,
                    skip_reason="fast_path",
                    end_to_end_ms=fp_result.end_to_end_ms,
                    saved_planner_tokens=fp_result.saved_planner_tokens,
                    saved_renderer_tokens=fp_result.saved_renderer_tokens,
                    saved_total_tokens=fp_result.saved_total_tokens,
                )
                trace_token = set_active_trace(trace)
                logger.info(
                    "request.trace",
                    trace=trace.model_dump(),
                )
                reset_active_trace(trace_token)

                return (
                    fp_result.response,
                    0,
                    [],
                    {
                        "fast_path_tokens": 0,
                        "saved_planner_tokens": fp_result.saved_planner_tokens,
                        "saved_renderer_tokens": fp_result.saved_renderer_tokens,
                        "saved_total_tokens": fp_result.saved_total_tokens,
                        "fast_path_type": fp_result.fast_path_type,
                    },
                )
            # Miss → fall through to full LLM path (fixes booking routing bug)
            logger.info(
                "fast_path.miss_fallthrough",
                intent=intent,
                note="Routing to llm_path — no social pattern matched.",
            )

        return await self._execute_llm_path(user_input, intent, payload, session_id)

    def _sanitize_tool_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Semantic Firewall (Layer 2): Sanitizes structured tool outputs.
        Note: Layer 1 happens in handle_tool_calls where it checks for '[REDACTED' strings.
        This Layer 2 filters dict keys to prevent indirect prompt injection, 
        using exact matching to avoid blocking safe keys like 'duration' or 'door_number'.
        """
        forbidden_keys = {"instruction", "command", "task", "execute", "run", "do"}
        sanitized = []
        
        for result in results:
            clean_item = {}
            # Match the 'output' key used in handle_tool_calls
            raw_data = result.get("output", {})
            if isinstance(raw_data, dict):
                for k, v in raw_data.items():
                    if k.lower() in forbidden_keys:
                        continue
                    if isinstance(v, str) and (v.strip().startswith("SYSTEM:") or v.strip().startswith("USER:")):
                        v = "[REDACTED: POTENTIAL INJECTION]"
                    clean_item[k] = v
                result["output"] = clean_item
            sanitized.append(result)
            
        return sanitized

    async def _execute_step(self, response: LLMResponse, session_id: Any, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Deterministic execution of tool calls with semantic firewall."""
        if not response.tool_calls:
            return []
        raw_results = await self.handle_tool_calls(response, session_id=session_id, user_id=user_id)
        return self._sanitize_tool_results(raw_results)

    async def _plan_step(
        self, request: LLMRequest, tool_hint: Optional[str], session_id: Any
    ) -> LLMResponse:
        """Determines if tools are needed. Enforcement happens AFTER a failed first attempt."""
        response = await self.generate_response(request, session_id=session_id)

        # Enforcement: Trigger ONLY if the model failed to call the required tool
        if tool_hint and not self._is_valid_tool_call(response.tool_calls, tool_hint):
            for attempt in range(2):
                logger.warning(
                    "planner.enforcement.retry",
                    extra={"tool": tool_hint, "attempt": attempt + 1},
                )
                # On retry, we use 'required' logic to force the model
                retry_request = LLMRequest(
                    model=request.model,
                    system_prompt=(
                        request.system_prompt +
                        f"\n\n[CRITICAL: You MUST call the '{tool_hint}' tool now. Text responses are forbidden.]"
                    ),
                    history=request.history,
                    user_input=request.user_input,
                    tool_choice=f"required:{tool_hint}", # Provider handles compatibility
                    metadata=request.metadata,
                )
                response = await self.generate_response(retry_request, session_id=session_id)
                if self._is_valid_tool_call(response.tool_calls, tool_hint):
                    break

        return response

    async def _render_step(
        self, request: LLMRequest, tool_results: list, session_id: Any, renderer_prompt: str
    ) -> LLMResponse:
        """Final synthesis turn (Blind Renderer)."""
        synthesis_request = LLMRequest(
            model=request.model,
            system_prompt=renderer_prompt,
            history=request.history,
            user_input=request.user_input,
            tool_results=tool_results,
            metadata=request.metadata,
        )
        return await self.generate_response(synthesis_request, session_id=session_id)

    async def _execute_llm_path(
        self, user_input: str, intent: str, payload: dict, session_id: Any
    ) -> tuple[str, int, list[dict], dict[str, int]]:
        """Coordinates the 3 Engines with Soft-First Enforcement and Full Observability."""
        pipeline_start = time.perf_counter()

        # 1. Initialize Tracing
        trace_id = set_trace_id()
        trace = RequestTrace(trace_id=trace_id, planner_executed=True)
        trace_token = set_active_trace(trace)

        tool_hint = INTENT_TOOL_MAP.get(intent)

        current_date_str = datetime.now().strftime("%Y-%m-%d %A")
        system_clock_str = f"\n\n[SYSTEM CLOCK: Today is {current_date_str}]"

        sys_prompt = payload.get("system_prompt", PromptLoader.get_default_system())
        if "[SYSTEM CLOCK" not in sys_prompt:
            sys_prompt += system_clock_str

        # Initial Request: Natural reasoning (Soft)
        request = LLMRequest(
            model=payload["model"],
            system_prompt=sys_prompt,
            history=self.response_validator.sanitize_history(payload.get("history", [])),
            user_input=user_input,
            tool_choice="auto",  # Let the model decide naturally first
            metadata={"intent": intent, "session_id": session_id},
        )

        total_tokens = 0
        token_breakdown: Dict[str, Any] = {
            "planner_prompt_tokens": 0,
            "planner_completion_tokens": 0,
            "renderer_prompt_tokens": 0,
            "renderer_completion_tokens": 0,
            "tool_result_tokens": 0,
        }

        # ── Step 1: PLANNER ENGINE ────────────────────────────────────────
        layer_token = set_trace_layer("planner")
        start_ms = time.perf_counter()
        plan_response = await self._plan_step(request, tool_hint, session_id)
        trace.layers["planner"].total_ms = round((time.perf_counter() - start_ms) * 1000, 2)
        reset_trace_layer(layer_token)

        plan_toks = plan_response.prompt_tokens + plan_response.completion_tokens
        total_tokens += plan_toks
        token_breakdown["planner_prompt_tokens"] = plan_response.prompt_tokens
        token_breakdown["planner_completion_tokens"] = plan_response.completion_tokens

        if tool_hint and not self._is_valid_tool_call(plan_response.tool_calls, tool_hint):
            logger.error("tool.enforcement.failed", extra={"intent": intent, "tool": tool_hint})
            trace.end_to_end_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
            logger.info("request.trace", trace=trace.model_dump())
            reset_active_trace(trace_token)
            return "عذراً، حدث خطأ مؤقت. من فضلك حاول مرة أخرى. 🙏", total_tokens, [], token_breakdown

        tool_results: List[Dict[str, Any]] = []

        # ── Step 2: EXECUTION ENGINE (with Semantic Firewall) ─────────────
        if plan_response.tool_calls:
            layer_token = set_trace_layer("execution")
            start_ms = time.perf_counter()
            user_id = payload.get("context").user_id if payload.get("context") else None
            tool_results = await self._execute_step(plan_response, session_id, user_id=user_id)
            trace.layers["execution"].total_ms = round((time.perf_counter() - start_ms) * 1000, 2)
            reset_trace_layer(layer_token)

        # ── Step 3: CONDITIONAL RENDERER ENGINE ──────────────────────────
        if plan_response.tool_calls:
            # OPTIMIZATION: Strip heavy fields before passing to Renderer
            renderer_tool_results = copy.deepcopy(tool_results)
            for tr in renderer_tool_results:
                if "output" in tr and isinstance(tr["output"], dict):
                    if "events" in tr["output"] and isinstance(tr["output"]["events"], list):
                        for ev in tr["output"]["events"]:
                            if isinstance(ev, dict):
                                ev.pop("short_description", None)

            if hasattr(self.response_generator.provider, "count_tokens"):
                tool_toks = await self.response_generator.provider.count_tokens(str(renderer_tool_results))
            else:
                tool_toks = len(str(renderer_tool_results)) // 4

            trace.tool_result_tokens = tool_toks
            if tool_toks > 1500:
                logger.warning("tool_results_too_large", tool_result_tokens=tool_toks, session_id=session_id)

            token_breakdown["tool_result_tokens"] = tool_toks

            # ── Template path: try to skip the Renderer entirely ──────────
            template_result = self.template_engine.match(tool_results)

            if template_result is not None:
                # Renderer skipped — return template response directly
                trace.renderer_skipped = True
                trace.renderer_executed = False
                trace.skip_reason = template_result.skip_reason
                trace.saved_renderer_tokens = template_result.saved_renderer_tokens
                trace.saved_total_tokens = template_result.saved_renderer_tokens
                trace.end_to_end_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)

                token_breakdown["renderer_prompt_tokens"] = 0
                token_breakdown["renderer_completion_tokens"] = 0
                token_breakdown["saved_renderer_tokens"] = template_result.saved_renderer_tokens

                logger.info(
                    "renderer.skipped",
                    skip_reason=template_result.skip_reason,
                    saved_tokens=template_result.saved_renderer_tokens,
                    session_id=session_id,
                )
                logger.info("request.trace", trace=trace.model_dump())
                reset_active_trace(trace_token)
                return template_result.response, total_tokens, tool_results, token_breakdown

            # ── Renderer path: full synthesis LLM call ────────────────────
            trace.renderer_executed = True
            layer_token = set_trace_layer("renderer")
            start_ms = time.perf_counter()
            renderer_prompt = payload.get("renderer_prompt", PromptLoader.load("synthesis_policy"))
            if "[SYSTEM CLOCK" not in renderer_prompt:
                renderer_prompt += system_clock_str
            render_response = await self._render_step(request, renderer_tool_results, session_id, renderer_prompt)
            trace.layers["renderer"].total_ms = round((time.perf_counter() - start_ms) * 1000, 2)
            reset_trace_layer(layer_token)

            render_toks = render_response.prompt_tokens + render_response.completion_tokens
            total_tokens += render_toks
            token_breakdown["renderer_prompt_tokens"] = render_response.prompt_tokens
            token_breakdown["renderer_completion_tokens"] = render_response.completion_tokens

            trace.end_to_end_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
            logger.info("request.trace", trace=trace.model_dump())
            reset_active_trace(trace_token)
            return render_response.content, total_tokens, tool_results, token_breakdown

        trace.end_to_end_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
        logger.info("request.trace", trace=trace.model_dump())
        reset_active_trace(trace_token)
        return plan_response.content, total_tokens, [], token_breakdown

    # -------------------------------------------------------------------------
    # _execute_fast_path — DEPRECATED
    # -------------------------------------------------------------------------
    # This method was the original, incomplete fast-path handler.  It only had
    # a special case for "greeting" and silently fell through to a barebones
    # LLM call (no tools, no system prompt) for all other intents — including
    # "booking", which the IntentRouter also routed to fast_path.
    #
    # BUG (pre-fix):
    #   intent=booking → route=fast_path → _execute_fast_path()
    #   → no greeting match → LLMRequest(system_prompt="Quick assistant.", tools=None)
    #   → booking attempt answered without search_events / create_booking tools
    #   → nonsensical or hallucinated response
    #
    # FIX:
    #   generate_complex() now calls FastPathRouter.match() instead.
    #   FastPathRouter handles only social intents (greeting/identity/thanks/goodbye).
    #   Any other intent (including booking) that arrives via route=fast_path
    #   gets a FastPathRouter miss and falls through to _execute_llm_path(),
    #   where the full Planner + tool + Renderer pipeline runs correctly.
    #
    # This method is retained for reference and backward compatibility but is
    # no longer called by generate_complex().
    async def _execute_fast_path(  # noqa: dead-code
        self, user_input: str, intent: str
    ) -> tuple[str, int, List[Dict[str, Any]], dict[str, int]]:
        """[DEPRECATED] Superseded by FastPathRouter + generate_complex() dispatch."""
        if intent == "greeting":
            content = "أهلا بيك! أقدر أساعدك في إيه؟"
            return content, 0, [], {"fast_path_tokens": 0}

        request = LLMRequest(
            model=settings.GEMINI_MODEL,
            system_prompt="Quick assistant.",
            history=[],
            user_input=user_input,
        )
        response = await self.generate_response(request)
        tool_results = await self.handle_tool_calls(response, session_id=None)
        content = response.content
        if tool_results:
            content = f"Action completed: {tool_results[0].get('output')}"

        toks = response.prompt_tokens + response.completion_tokens
        return content, toks, tool_results, {"fast_path_tokens": toks}
