from __future__ import annotations

import logging
import time
from typing import Any

from app.ai.providers.base import LLMRequest, LLMResponse
from app.ai.response_generator import ResponseGenerator
from app.ai.safety import ResponseValidator
from app.ai.tool_registry import ToolRegistry
from app.core.exceptions import LLMUnavailableException
from app.core.observability import get_logger

logger = get_logger(__name__)


class AIOrchestrator:
    """
    The AIOrchestrator manages the flow of generating AI responses.
    It coordinates between the ResponseGenerator, ToolRegistry, and ResponseValidator.
    """

    def __init__(
        self,
        response_generator: ResponseGenerator,
        response_validator: ResponseValidator,
        tool_registry: ToolRegistry | None = None,
        runtime_deps: dict[str, Any] | None = None,
    ):
        """
        Initializes the orchestrator with necessary components.
        
        Args:
            response_generator: The engine that generates text from the AI model.
            response_validator: Ensures the AI response is safe and follows rules.
            tool_registry: A collection of tools the AI can use to perform actions.
            runtime_deps: Extra data needed at runtime (like current user info).
        """
        self.response_generator = response_generator
        self.response_validator = response_validator
        self.tool_registry = tool_registry
        self.runtime_deps = runtime_deps or {}

    async def generate_response(
        self, 
        request: LLMRequest,
        session_id: int | None = None
    ) -> LLMResponse:
        """
        Main method to generate a response from the AI.
        It adds tool definitions to the request and logs performance data.
        """
        start_time = time.perf_counter()
        
        # If we have a tool registry, tell the AI what tools are available.
        if self.tool_registry:
            request.metadata = request.metadata or {}
            request.metadata["tools"] = self.tool_registry.get_tool_definitions()

        try:
            # Step 1: Send the request to the AI model.
            response = await self.response_generator.generate(request)
            latency = time.perf_counter() - start_time
            
            # Step 2: Log the results for monitoring (tokens used, latency, etc.)
            logger.info(
                "ai.generation.completed",
                session_id=session_id,
                latency_ms=round(latency * 1000, 2),
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                finish_reason=response.finish_reason,
                has_tool_calls=bool(response.tool_calls)
            )

            # Step 3: If the AI returned text (not a tool call), validate it for safety.
            if not response.tool_calls:
                response.content = self.response_validator.validate_response(response.content)

            return response
            
        except Exception as exc:
            # Log any errors that occur during the process.
            latency = time.perf_counter() - start_time
            logger.error(
                "ai.generation.failed",
                session_id=session_id,
                latency_ms=round(latency * 1000, 2),
                error=str(exc)
            )
            raise

    async def handle_tool_calls(self, response: LLMResponse) -> list[dict[str, Any]]:
        """
        If the AI decides to use a tool (like 'get_events'), this method executes those tools.
        It returns the results of the tool executions.
        """
        # If there are no tool calls or no registry, there's nothing to do.
        if not response.tool_calls or not self.tool_registry:
            return []

        results = []
        # Loop through each tool call requested by the AI.
        for call in response.tool_calls:
            name = call.get("name")
            args = call.get("arguments", {})
            call_id = call.get("id")
            
            try:
                # Execute the tool and capture the result.
                result = await self.tool_registry.call_tool(
                    name,
                    runtime_deps=self.runtime_deps,
                    **args
                )
                results.append({
                    "tool_call_id": call_id,
                    "tool_name": name,
                    "output": result
                })
            except Exception as exc:
                # If a tool fails, record the error.
                logger.error("tool.call.failed", tool=name, error=str(exc))
                results.append({
                    "tool_call_id": call_id,
                    "tool_name": name,
                    "error": str(exc)
                })
        
        return results

    async def generate_complex(
        self, 
        user_input: str, 
        intent: str, 
        payload: dict, 
        session_id: Any,
        route: str = "llm_path"
    ) -> tuple[str, int, list[dict]]:
        """
        Unified orchestration for complex AI generation.
        Handles fast paths, standard LLM paths, and tool call synthesis.
        """
        if route == "fast_path":
            return await self._execute_fast_path(user_input, intent)
            
        return await self._execute_llm_path(user_input, intent, payload, session_id)

    async def _execute_llm_path(self, user_input: str, intent: str, payload: dict, session_id: Any) -> tuple[str, int, list[dict]]:
        """Standard LLM reasoning path with tool support."""
        system_prompt = payload.get("system_prompt", "") 
        request = LLMRequest(
            model=payload["model"],
            system_prompt=system_prompt,
            history=payload.get("history", []),
            user_input=user_input,
            metadata={"intent": intent, "session_id": session_id},
        )
        
        tokens_used = 0
        response = await self.generate_response(request, session_id=session_id)
        tokens_used += response.completion_tokens
        
        tool_results = await self.handle_tool_calls(response)
        
        if tool_results:
            # Multi-turn synthesis
            tool_context = f"\n\n[SYSTEM: Tool results: {tool_results}. Please synthesize the final response.]"
            request.user_input += tool_context
            final_response = await self.generate_response(request, session_id=session_id)
            response.content = final_response.content
            tokens_used += final_response.completion_tokens
            
        return response.content, tokens_used, tool_results

    async def _execute_fast_path(self, user_input: str, intent: str) -> tuple[str, int, list[dict]]:
        """Optimized path for simple transactional intents."""
        request = LLMRequest(
            model="gemini-2.0-flash", 
            system_prompt=f"Quick assistant. Intent: {intent}.",
            history=[], 
            user_input=user_input,
        )
        
        response = await self.generate_response(request)
        tool_results = await self.handle_tool_calls(response)
        
        content = response.content
        if tool_results:
            content = f"Action completed: {tool_results[0].get('output')}"
            
        return content, response.completion_tokens, tool_results
