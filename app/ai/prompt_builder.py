from __future__ import annotations
from typing import Optional, Union, Any
from app.ai.prompt_loader import PromptLoader
from app.core.config import settings
from app.schemas.chat_dtos import ChatContext

class PromptBuilder:
    def build_system_prompt(self, context: ChatContext, detected_intent: Optional[str] = None) -> str:
        parts = [PromptLoader.load("core_system")]
        
        # Determine active intent
        intent = detected_intent or context.current_intent
        
        # Load phase-specific rules based on intent
        if intent == "booking":
            parts.append(PromptLoader.load("phase_booking"))
        elif intent == "manage_booking":
            parts.append(PromptLoader.load("phase_management"))
        elif intent == "discover":
            parts.append(PromptLoader.load("phase_discovery"))
            

        if context.current_summary:
            parts.append(f"Conversation summary:\n{context.current_summary}")
        if context.current_intent:
            parts.append(f"Current session intent: {context.current_intent}")
        if detected_intent:
            parts.append(f"Detected user intent for this turn: {detected_intent}")
        if context.channel:
            parts.append(f"Channel: {context.channel}")
        return "\n\n".join(parts)

    def build_renderer_prompt(self, context: ChatContext) -> str:
        """Isolated prompt specifically for the Renderer Engine."""
        parts = [PromptLoader.load("synthesis_policy")]
        
        # Only add metadata, NO full rules or identity.
        if context.current_summary:
            parts.append(f"Conversation summary:\n{context.current_summary}")
        return "\n\n".join(parts)

    def build_history(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # History is already trimmed to CHAT_MAX_HISTORY by ChatMemoryService
        return messages
