import uuid
import logging
from typing import Any, Dict, List
from app.core.config import settings
from app.core.ports.state import StatePort
from app.core.background_task_utils import fire_and_forget
from app.schemas.chat_dtos import ChatContext


class ChatMemoryService:
    """
    Application Layer Memory Service.
    Handles the logic of conversation history and state management.
    Uses StatePort for low-level storage access.
    """

    def __init__(self, state_port: StatePort, message_service: Any = None, arq_pool: Any = None):
        self.logger = logging.getLogger(__name__)
        self.state = state_port
        self.messages = message_service
        self.arq_pool = arq_pool

    async def get_conversation_context(self, session_id: uuid.UUID, current_message: str) -> Dict[str, Any]:
        """Loads and prepares context for the AI domain. Uses DB as fallback for history."""
        state_key = f"chat:session:{session_id}:context"
        
        try:
            context_data = await self.state.get_state(state_key) or {}
        except Exception as e:
            self.logger.warning(f"Failed to read context from Redis: {e}")
            context_data = {}
            
        history = await self._get_reliable_history(session_id)
        
        # Map last_intent to current_intent if exists
        if "last_intent" in context_data and "current_intent" not in context_data:
            context_data["current_intent"] = context_data.pop("last_intent")
            
        try:
            context = ChatContext(**context_data)
        except Exception as e:
            self.logger.warning(f"Failed to parse ChatContext (schema drift?): {e}")
            context = ChatContext()
            
        # Opaque context construction
        return {
            "history": history, 
            "context": context,
            "message": current_message
        }

    async def _get_reliable_history(self, session_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Source of Truth: Redis Cache -> Postgres Fallback."""
        history_key = f"chat:session:{session_id}:history"
        try:
            history = await self.state.get_state(history_key)
        except Exception as e:
            self.logger.warning(f"Redis read failed for history, falling back to DB: {e}")
            history = None
        
        if history is not None:
            return history[-settings.CHAT_MAX_HISTORY:]
            
        # Fallback to DB if Redis is empty/expired
        if self.messages:
            db_messages = await self.messages.get_session_history(session_id, limit=settings.CHAT_MAX_HISTORY)
            history = [{"role": m.role, "content": m.content} for m in db_messages]
            # Warm up cache (fire-and-forget: no need to block the response)
            # NOTE: If called concurrently without external lock, could result
            # in redundant concurrent cache writes (Last Write Wins).
            fire_and_forget(
                self.state.set_state(history_key, history, ttl=86400),
                name=f"cache_warm_history:{session_id}",
            )
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
        
        # 1. Optimistic History Update (Write-Through)
        try:
            history = await self.state.get_state(history_key)
            if history is not None:
                history.append({"role": "user", "content": user_msg})
                history.append({"role": "assistant", "content": assistant_msg})
                history = history[-settings.CHAT_MAX_HISTORY:]
                await self.state.set_state(history_key, history, ttl=86400)
        except Exception as e:
            self.logger.warning(f"Failed to optimistically update redis history: {e}")

        # 2. Update Intent/Context
        context_key = f"chat:session:{session_id}:context"
        # NOTE: This read-modify-write pattern on the JSON blob is susceptible
        # to a lost update anomaly if `save_summary` runs concurrently (e.g., from ARQ worker).
        # A future improvement could use Redis HSET for atomic field updates.
        try:
            context = await self.state.get_state(context_key) or {}
            context["current_intent"] = intent
            await self.state.set_state(context_key, context, ttl=604800) # 7d TTL
        except Exception as e:
            self.logger.warning(f"Failed to optimistically update redis context: {e}")

        # 3. Handle Counter & Bucket-based Summarization Decision
        # Atomic Increment & Enqueue: 
        # Atomicity between increment and set_nx ensures we only enqueue one job per bucket.
        should_summarize = False
        try:
            new_count = await self.state.increment(count_key, ttl=86400)
            
            bucket = new_count // 10
            if bucket > 0 and getattr(self, "arq_pool", None):
                bucket_key = f"processed_summary_bucket:{session_id}:{bucket}"
                # Atomic SETNX: returns True if key was set, False if it existed
                if await self.state.set_nx(bucket_key, "enqueued", ttl=86400 * 7):
                    # NOTE: If enqueue_job fails here, the bucket is skipped because
                    # increment succeeded but the job wasn't queued. Future increments
                    # will move past this bucket. This is an accepted edge case.
                    await self.arq_pool.enqueue_job(
                        "summarize_session_job",
                        str(session_id),
                        new_count,
                        _job_id=f"summarize:{session_id}:bucket:{bucket}"
                    )
                    should_summarize = True
        except Exception as e:
            self.logger.warning(f"Failed to enqueue summarization job: {e}")

        return should_summarize, []

    async def save_summary(self, session_id: uuid.UUID, summary: str) -> None:
        """Saves generated summary back to context memory."""
        context_key = f"chat:session:{session_id}:context"
        # NOTE: Like persist_interaction, this read-modify-write could lose updates
        # if `persist_interaction` happens concurrently. HSET would be safer.
        try:
            context = await self.state.get_state(context_key) or {}
            context["current_summary"] = summary
            await self.state.set_state(context_key, context, ttl=604800) # 7d TTL
        except Exception as e:
            self.logger.error(f"Failed to save summary to Redis: {e}")
