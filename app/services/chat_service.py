from __future__ import annotations
import logging
import time
from typing import Any, Dict

from app.core.perf_tracer import PerformanceTracer

from app.core.observability import get_logger

from app.ai.intent_detector import IntentDetector
from app.ai.intent_router import IntentRouter
from app.ai.prompt_builder import PromptBuilder
from app.models.chatbot.message import MessageRole
from app.schemas.chat_dtos import ChatDomainRequest, ChatDomainResponse
from app.services.ai_orchestrator import AIOrchestrator

logger = get_logger(__name__)


class ChatService:
    """
    100% Agnostic Domain Service.
    Operates on pure AI logic and returns domain results with opaque metadata.
    """

    def __init__(
        self,
        ai_orchestrator: AIOrchestrator,
        intent_detector: IntentDetector,
        intent_router: IntentRouter,
        prompt_builder: PromptBuilder,
    ):
        self.orchestrator = ai_orchestrator
        self.intent_detector = intent_detector
        self.intent_router = intent_router
        self.prompt_builder = prompt_builder

    async def generate_response(
        self,
        domain_request: ChatDomainRequest,
    ) -> ChatDomainResponse:
        """
        AI Domain Pipeline.
        Returns result and metadata that the Application Layer interprets.
        """
        tracer = PerformanceTracer()
        
        # 1. Intent & Routing
        with tracer.step("intent_detection"):
            intent_result = await self.intent_detector.detect_complex(domain_request.message)
            routing = self.intent_router.route(intent_result)
        logger.info("chat.intent_detected", intent=routing["intent"], confidence=routing["confidence"], route=routing["route"])
        
        # 2. Construction
        with tracer.step("prompt_construction"):
            system_prompt = self.prompt_builder.build_system_prompt(domain_request.context, routing["intent"])
            renderer_prompt = self.prompt_builder.build_renderer_prompt(domain_request.context)
            history_formatted = self.prompt_builder.build_history(domain_request.history)

        # 3. Generation
        logger.info("chat.generation_started", intent=routing["intent"], route=routing["route"])
        with tracer.step("ai_generation"):
            content, ai_tokens, tools, token_breakdown = await self.orchestrator.generate_complex(
                user_input=domain_request.message,
                intent=routing["intent"],
                payload={
                    "system_prompt": system_prompt,
                    "renderer_prompt": renderer_prompt,
                    "history": history_formatted,
                    "context": domain_request.context,
                    "model": domain_request.context.model_name
                },
                session_id=domain_request.context.session_id,
                route=routing["route"]
            )
            
            # Add intent tokens to the breakdown
            intent_tokens = intent_result.get("tokens", 0) if intent_result else 0
            token_breakdown["intent_tokens"] = intent_tokens
            ai_tokens += intent_tokens

        # 4. Result Construction (Agnostic Metadata)
        tracer.log_summary(logger, layer="domain", session_id=domain_request.context.session_id)
        return ChatDomainResponse(
            content=content,
            role=MessageRole.assistant,
            intent=routing["intent"],
            confidence=routing["confidence"],
            route=routing["route"],
            ai_tokens=ai_tokens,
            tool_results=tools,
            latency_ms=int(tracer.total_ms),
            token_breakdown=token_breakdown
        )
