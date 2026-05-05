from __future__ import annotations

from typing import Any

from app.schemas.chat_dtos import ChatContext


class PromptBuilder:
    def build_system_prompt(self, context: ChatContext, detected_intent: str | None = None) -> str:
        parts = []
        if context.system_prompt:
            parts.append(context.system_prompt)
            
        parts.append(
            "--- SYSTEM ARCHITECTURE CONSTRAINTS ---\n"
            "The main booking platform remains the source of truth for transactional and financial operations. "
            "Use the chatbot database only as context and projection data."
        )
        if context.current_summary:
            parts.append(f"Conversation summary:\n{context.current_summary}")
        if context.current_intent:
            parts.append(f"Current session intent: {context.current_intent}")
        if detected_intent:
            parts.append(f"Detected user intent for this turn: {detected_intent}")
        if context.channel:
            parts.append(f"Channel: {context.channel}")
        return "\n\n".join(parts)

    def build_history(self, messages: list[dict[str, Any]], max_messages: int = 12) -> list[dict[str, Any]]:
        return messages[-max_messages:]
