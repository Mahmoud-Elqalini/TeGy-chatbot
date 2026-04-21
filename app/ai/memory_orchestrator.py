from __future__ import annotations
import logging
from typing import Optional
from app.ai.memory_manager import MemoryManager, SessionContext

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    def __init__(self, memory: MemoryManager):
        self._mem = memory

    async def load_session_memory(
        self,
        session_id: str,
    ) -> tuple[Optional[SessionContext], list[dict]]:
        context  = await self._mem.load_context(session_id)
        messages = await self._mem.load_messages(session_id)
        return context, messages

    async def after_user_message(
        self,
        session_id: str,
        content: str,
    ) -> bool:
        await self._mem.save_message(session_id, "user", content)
        should_summarize = await self._mem.should_summarize(session_id)
        if not should_summarize:
            return False
            
        locked = await self._mem.acquire_summarize_lock(session_id)
        if not locked:
            logger.warning("session %s is already being summarized (lock acquired by another process)", session_id)
            return False
            
        logger.info("acquired summarize lock for session %s", session_id)
        return True

    async def after_assistant_message(
        self,
        session_id: str,
        content: str,
        new_intent: Optional[str] = None,
    ) -> None:
        await self._mem.save_message(session_id, "assistant", content)
        if new_intent:
            await self._mem.update_intent(session_id, new_intent)

    async def after_summarization(
        self,
        session_id: str,
        summary: str,
    ) -> None:
        await self._mem.update_summary(session_id, summary)
        await self._mem.reset_counter(session_id)
        logger.info("summary updated for session %s", session_id)

    async def build_llm_payload(
        self,
        session_id: str,
        user_message: str,
        max_tokens: int = 3000,
    ) -> Optional[dict]:
        context, messages = await self.load_session_memory(session_id)
        if context is None:
            logger.error("no context found for session %s", session_id)
            return None

        system  = self._build_system(context)
        history = self._build_history(messages, max_tokens)

        return {
            "model":      context.model_name,
            "system":     system,
            "history":    history,
            "user_input": user_message,
        }

    def _build_system(self, context: SessionContext) -> str:
        parts = []
        if context.system_prompt:
            parts.append(context.system_prompt)
        if context.current_summary:
            parts.append(
                f"conversation summary so far:\n{context.current_summary}"
            )
        if context.current_intent:
            parts.append(
                f"current user intent: {context.current_intent}"
            )
        return "\n\n".join(parts)

    def _build_history(
        self,
        messages: list[dict],
        max_tokens: int,
    ) -> list[dict]:
        token_count = 0
        trimmed     = []
        for msg in messages:
            content = msg.get("content", "")
            estimated = int(len(content.split()) * 1.3)
            if token_count + estimated > max_tokens:
                break
            trimmed.append(msg)
            token_count += estimated
        return trimmed[::-1]

    async def end_session(self, session_id: str) -> None:
        await self._mem.clear_session(session_id)
        logger.info("session %s cleared from memory", session_id)