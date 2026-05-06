import uuid
import json
from typing import Any, Dict, List
from app.core.config import settings
from app.core.ports.state import StatePort
from app.schemas.chat_dtos import ChatContext


class ChatMemoryService:
    """
    Application Layer Memory Service.
    Handles the logic of conversation history and state management.
    Uses StatePort for low-level storage access.
    """

    def __init__(self, state_port: StatePort, message_service: Any = None, arq_pool: Any = None):
        self.state = state_port
        self.messages = message_service
        self.arq_pool = arq_pool

    async def get_conversation_context(self, session_id: uuid.UUID, current_message: str) -> Dict[str, Any]:
        """Loads and prepares context for the AI domain. Uses DB as fallback for history."""
        state_key = f"chat:session:{session_id}:context"
        
        context_data = await self.state.get_state(state_key) or {}
        history = await self._get_reliable_history(session_id)
        
        # Map last_intent to current_intent if exists
        if "last_intent" in context_data and "current_intent" not in context_data:
            context_data["current_intent"] = context_data.pop("last_intent")
            
        # Opaque context construction
        return {
            "history": history, 
            "context": ChatContext(**context_data),
            "message": current_message
        }

    async def _get_reliable_history(self, session_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Source of Truth: Redis Cache -> Postgres Fallback."""
        history_key = f"chat:session:{session_id}:history"
        history = await self.state.get_state(history_key)
        
        if history is not None:
            return history[-settings.CHAT_MAX_HISTORY:]
            
        # Fallback to DB if Redis is empty/expired
        if self.messages:
            db_messages = await self.messages.get_session_history(session_id, limit=settings.CHAT_MAX_HISTORY)
            history = [{"role": m.role, "content": m.content} for m in db_messages]
            # Warm up cache
            await self.state.set_state(history_key, history, ttl=86400)
            return history
            
        return []



    async def persist_interaction(
        self, 
        session_id: uuid.UUID, 
        user_msg: str, 
        assistant_msg: str, 
        intent: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Persists the interaction and decides if summarization is needed."""
        history_key = f"chat:session:{session_id}:history"
        count_key = f"chat:session:{session_id}:count"
        
        # 1. Update History Cache (Point 1 Hardening: Pure Cache Invalidation)
        # Instead of full history rebuild or mutated append, we invalidate the cache.
        # This ensures the DB remains the ONLY source of truth.
        # The next 'get_conversation_context' will refill the cache from DB.
        await self.state.delete_state(history_key)

        # 2. Update Intent/Context
        context_key = f"chat:session:{session_id}:context"
        context = await self.state.get_state(context_key) or {}
        context["current_intent"] = intent
        await self.state.set_state(context_key, context, ttl=604800) # 7d TTL

        # 3. Handle Counter & Bucket-based Summarization Decision (Atomic 🔴)
        new_count = await self.state.increment(count_key, ttl=86400)
        
        should_summarize = False
        bucket = new_count // 10
        if bucket > 0 and getattr(self, "arq_pool", None):
            bucket_key = f"processed_summary_bucket:{session_id}:{bucket}"
            # Atomic SETNX: returns True if key was set, False if it existed
            if await self.state.set_nx(bucket_key, "enqueued", ttl=86400 * 7):
                await self.arq_pool.enqueue_job(
                    "summarize_session_job",
                    str(session_id),
                    new_count,
                    _job_id=f"summarize:{session_id}:bucket:{bucket}"
                )
                should_summarize = True

        return should_summarize, []

    async def save_summary(self, session_id: uuid.UUID, summary: str) -> None:
        """Saves a summary to the state store."""
        context_key = f"chat:session:{session_id}:context"
        context = await self.state.get_state(context_key) or {}
        context["current_summary"] = summary
        await self.state.set_state(context_key, context, ttl=604800) # 7d TTL
