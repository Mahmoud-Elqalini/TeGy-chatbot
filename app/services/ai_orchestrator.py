from __future__ import annotations
from app.core.config import settings

import time
from typing import Any

from app.ai.providers.base import LLMRequest, LLMResponse
from app.ai.response_generator import ResponseGenerator
from app.ai.safety import ResponseValidator
from app.ai.tool_registry import ToolRegistry
from app.core.observability import get_logger

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
        tool_registry: ToolRegistry | None = None,
        runtime_deps: dict[str, Any] | None = None,
    ):
        self.response_generator = response_generator
        self.response_validator = response_validator
        self.tool_registry = tool_registry
        self.runtime_deps = runtime_deps or {}

    def _is_valid_tool_call(self, tool_calls: list | None, expected_tool: str) -> bool:
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
            request.tools = self.tool_registry.get_tool_definitions()
        return request

    async def generate_response(
        self,
        request: LLMRequest,
        session_id: int | None = None,
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

    async def handle_tool_calls(self, response: LLMResponse, session_id: Any = None) -> list[dict[str, Any]]:
        if not response.tool_calls or not self.tool_registry:
            return []

        results = []
        tool_deps = dict(self.runtime_deps)
        if session_id:
            tool_deps["session_id"] = session_id

        for call in response.tool_calls:
            name = call.get("name")
            args = call.get("arguments", {})
            call_id = call.get("id")

            try:
                logger.info("tool.execution_started", tool_name=name, call_id=call_id)
                result = await self.tool_registry.call_tool(
                    name, runtime_deps=tool_deps, **args
                )

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
    ) -> tuple[str, int, list[dict]]:
        if route == "fast_path":
            return await self._execute_fast_path(user_input, intent)
        return await self._execute_llm_path(user_input, intent, payload, session_id)

    def _sanitize_tool_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Semantic Firewall: Sanitizes tool outputs to prevent indirect prompt injection."""
        forbidden_keys = {"instruction", "command", "task", "execute", "run", "do"}
        sanitized = []
        
        for result in results:
            clean_item = {}
            # Match the 'output' key used in handle_tool_calls
            raw_data = result.get("output", {})
            if isinstance(raw_data, dict):
                for k, v in raw_data.items():
                    if any(f in k.lower() for f in forbidden_keys):
                        continue
                    if isinstance(v, str) and (v.strip().startswith("SYSTEM:") or v.strip().startswith("USER:")):
                        v = "[REDACTED: POTENTIAL INJECTION]"
                    clean_item[k] = v
                result["output"] = clean_item
            sanitized.append(result)
            
        return sanitized

    async def _execute_step(self, response: LLMResponse, session_id: Any) -> list[dict[str, Any]]:
        """Deterministic execution of tool calls with semantic firewall."""
        if not response.tool_calls:
            return []
        raw_results = await self.handle_tool_calls(response, session_id=session_id)
        return self._sanitize_tool_results(raw_results)

    async def _plan_step(
        self, request: LLMRequest, tool_hint: str | None, session_id: Any
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
                        settings.DEFAULT_SYSTEM_PROMPT +
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
        self, request: LLMRequest, tool_results: list, session_id: Any
    ) -> LLMResponse:
        """Final synthesis turn (Blind Renderer)."""
        synthesis_request = LLMRequest(
            model=request.model,
            system_prompt=(
                settings.DEFAULT_SYSTEM_PROMPT +
                "\n\nCONTEXTUAL DATA POLICY:\n"
                "- Use ONLY the data provided below.\n"
                "- Do NOT mention 'tools' or 'retrieval'.\n"
                "- If data is insufficient, explain naturally."
            ),
            history=request.history,
            user_input=request.user_input,
            tool_results=tool_results,
            metadata=request.metadata,
        )
        return await self.generate_response(synthesis_request, session_id=session_id)

    async def _execute_llm_path(
        self, user_input: str, intent: str, payload: dict, session_id: Any
    ) -> tuple[str, int, list[dict]]:
        """Coordinates the 3 Engines with Soft-First Enforcement."""
        
        tool_hint = INTENT_TOOL_MAP.get(intent)

        # Initial Request: Natural reasoning (Soft)
        request = LLMRequest(
            model=payload["model"],
            system_prompt=settings.DEFAULT_SYSTEM_PROMPT,
            history=self.response_validator.sanitize_history(payload.get("history", [])),
            user_input=user_input,
            tool_choice="auto", # Let the model decide naturally first
            metadata={"intent": intent, "session_id": session_id},
        )

        total_tokens = 0

        # Step 1: PLANNER ENGINE (Soft first, then Hard on retry)
        plan_response = await self._plan_step(request, tool_hint, session_id)
        total_tokens += plan_response.prompt_tokens + plan_response.completion_tokens

        if tool_hint and not self._is_valid_tool_call(plan_response.tool_calls, tool_hint):
            logger.error("tool.enforcement.failed", extra={"intent": intent, "tool": tool_hint})
            return "عذراً، حدث خطأ مؤقت. من فضلك حاول مرة أخرى. 🙏", total_tokens, []

        # Step 2: EXECUTION ENGINE (with Semantic Firewall)
        tool_results = await self._execute_step(plan_response, session_id)

        # Step 3: RENDERER ENGINE
        if plan_response.tool_calls:
            render_response = await self._render_step(request, tool_results, session_id)
            total_tokens += render_response.prompt_tokens + render_response.completion_tokens
            return render_response.content, total_tokens, tool_results

        return plan_response.content, total_tokens, []

    async def _execute_fast_path(self, user_input: str, intent: str) -> tuple[str, int, list[dict]]:
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
        return content, response.completion_tokens, tool_results
        