import uuid
import json
from typing import Any, Dict, List
from app.core.ports.state import StatePort
from app.schemas.chat_dtos import ChatContext


class ChatMemoryService:
    """
    Application Layer Memory Service.
    Handles the logic of conversation history and state management.
    Uses StatePort for low-level storage access.
    """

    def __init__(self, state_port: StatePort):
        self.state = state_port

    async def get_conversation_context(self, session_id: uuid.UUID, current_message: str) -> Dict[str, Any]:
        """Loads and prepares context for the AI domain."""
        state_key = f"chat:session:{session_id}:context"
        history_key = f"chat:session:{session_id}:history"
        
        context_data = await self.state.get_state(state_key) or {}
        history = await self.state.get_state(history_key) or []
        
        # Map last_intent to current_intent if exists
        if "last_intent" in context_data and "current_intent" not in context_data:
            context_data["current_intent"] = context_data.pop("last_intent")
            
        # Opaque context construction
        return {
            "history": history[-20:], # Business decision: last 20 messages
            "context": ChatContext(**context_data),
            "message": current_message
        }

    MAX_HISTORY = 20

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
        
        # 1. Update History with Sliding Window 🟠
        history = await self.state.get_state(history_key) or []
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        
        # Enforce window 🟠
        history = history[-self.MAX_HISTORY:]
        await self.state.set_state(history_key, history, ttl=86400) # 24h TTL

        # 2. Update Intent/Context
        context_key = f"chat:session:{session_id}:context"
        context = await self.state.get_state(context_key) or {}
        context["current_intent"] = intent
        await self.state.set_state(context_key, context, ttl=604800) # 7d TTL

        # 3. Handle Counter & Summarization Decision (Atomic 🔴)
        new_count = await self.state.increment(count_key, ttl=86400)
        
        should_summarize = new_count % 10 == 0
        return should_summarize, history

    async def save_summary(self, session_id: uuid.UUID, summary: str) -> None:
        """Saves a summary to the state store."""
        context_key = f"chat:session:{session_id}:context"
        context = await self.state.get_state(context_key) or {}
        context["current_summary"] = summary
        await self.state.set_state(context_key, context, ttl=604800) # 7d TTL
        
        # Reset counter after summary (Set to 0 explicitly 🔴)
        count_key = f"chat:session:{session_id}:count"
        await self.state.set_state(count_key, 0, ttl=86400)
