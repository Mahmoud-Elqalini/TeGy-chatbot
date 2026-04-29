from __future__ import annotations
import logging
import time
from typing import Any, Dict

from app.ai.intent_detector import IntentDetector
from app.ai.intent_router import IntentRouter
from app.ai.prompt_builder import PromptBuilder
from app.models.chatbot.message import MessageRole
from app.schemas.chat_dtos import ChatDomainRequest, ChatDomainResponse
from app.services.ai_orchestrator import AIOrchestrator

logger = logging.getLogger(__name__)


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
        start_time = time.time()
        
        # 1. Intent & Routing
        intent_result = await self.intent_detector.detect_complex(domain_request.message)
        routing = self.intent_router.route(intent_result)
        
        # 2. Construction
        system_prompt = self.prompt_builder.build_system_prompt(domain_request.context, routing["intent"])
        history_formatted = self.prompt_builder.build_history(domain_request.history)

        # 3. Generation
        content, ai_tokens, tools = await self.orchestrator.generate_complex(
            user_input=domain_request.message,
            intent=routing["intent"],
            payload={
                "system_prompt": system_prompt,
                "history": history_formatted,
                "context": domain_request.context
            },
            session_id=None,
            route=routing["route"]
        )

        # 4. Result Construction (Agnostic Metadata)
        return ChatDomainResponse(
            content=content,
            role=MessageRole.assistant,
            intent=routing["intent"],
            confidence=routing["confidence"],
            route=routing["route"],
            ai_tokens=ai_tokens,
            tool_results=tools,
            latency_ms=int((time.time() - start_time) * 1000)
        )
