import uuid
from typing import Any, Dict
from app.core.ports.memory import MemoryPort
from app.ai.memory_manager import MemoryManager


class RedisMemoryAdapter(MemoryPort):
    """
    Infrastructure Adapter for Redis-based memory.
    Wraps MemoryManager to satisfy MemoryPort.
    """

    def __init__(self, memory_manager: MemoryManager):
        self.manager = memory_manager

    async def get_context(self, session_id: uuid.UUID, message: str) -> Dict[str, Any]:
        payload = await self.manager.build_llm_payload(session_id, message)
        return payload if payload else {}

    async def update_after_user(self, session_id: uuid.UUID, message: str) -> bool:
        return await self.manager.after_user_message(session_id, message)

    async def update_after_assistant(self, session_id: uuid.UUID, content: str, intent: str) -> None:
        await self.manager.after_assistant_message(session_id, content, intent)

    async def get_summary(self, session_id: uuid.UUID) -> str | None:
        return await self.manager.summarize_current_session(session_id)
