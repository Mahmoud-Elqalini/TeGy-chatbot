from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.redis import RedisClient, RedisKeys
from app.core.config import settings

logger = logging.getLogger(__name__)


class TTL:
    """
    Time To Live (TTL) constants for Redis data in seconds.
    """
    MESSAGES = 60 * 60 * 24        # Messages expire after 24 hours
    CONTEXT = 60 * 60 * 24 * 7     # Context expires after 7 days
    SUMMARY = 60 * 60 * 24 * 30    # Summaries expire after 30 days
    LOCK = 300                     # Locks expire after 5 minutes


MAX_MESSAGES = 20       # Keep only the last 20 messages in active memory
SUMMARIZE_EVERY = 10    # Create a summary every 10 messages


class SessionContext(BaseModel):
    """
    Represents the metadata and current state of a chat session.
    """
    model_config = ConfigDict(protected_namespaces=())

    session_id: str
    user_id: str
    user_source_id: str = ""
    channel: str = "web"
    current_intent: str = ""
    current_summary: str = ""
    model_name: str = Field(default=settings.GEMINI_MODEL)
    system_prompt: str = ""
    updated_at: str = ""
    version: int = 0

    @field_validator("session_id", "user_id")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        """Ensures that required IDs are not empty."""
        if not value.strip():
            raise ValueError("field cannot be empty")
        return value

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> "SessionContext":
        """Converts raw Redis data into a SessionContext object."""
        return cls(
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", ""),
            user_source_id=data.get("user_source_id", ""),
            channel=data.get("channel", "web"),
            current_intent=data.get("current_intent", ""),
            current_summary=data.get("current_summary", ""),
            model_name=data.get("model_name") or settings.GEMINI_MODEL,
            system_prompt=data.get("system_prompt", ""),
            updated_at=data.get("updated_at", ""),
            version=int(data.get("version", 0)),
        )

    def to_redis(self) -> dict[str, str]:
        """Converts the SessionContext object into a format suitable for Redis."""
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.version += 1
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_source_id": self.user_source_id,
            "channel": self.channel,
            "current_intent": self.current_intent,
            "current_summary": self.current_summary,
            "model_name": self.model_name,
            "system_prompt": self.system_prompt,
            "updated_at": self.updated_at,
            "version": str(self.version),
        }


class MemoryManager:
    """
    Manages chat memory using Redis. 
    Consolidated logic for both low-level Redis operations and high-level message lifecycle.
    """
    def __init__(self, redis: RedisClient):
        self._redis = redis

    # --- Low-Level Redis Operations ---

    async def load_context(self, session_id: str) -> Optional[SessionContext]:
        """Loads the session context from Redis."""
        data = await self._redis.hgetall(RedisKeys.session_context(session_id))
        if not data:
            return None
        try:
            return SessionContext.from_redis(data)
        except Exception:
            logger.exception("invalid redis context for session_id=%s", session_id)
            return None

    async def save_context(self, session_id: str, context: SessionContext) -> None:
        """Saves the entire session context to Redis."""
        key = RedisKeys.session_context(session_id)
        pipe = self._redis.pipeline()
        pipe.hset(key, mapping=context.to_redis())
        pipe.expire(key, TTL.CONTEXT)
        await pipe.execute()

    async def load_session_state(self, session_id: str) -> tuple[Optional[SessionContext], list[dict]]:
        """Loads both context and recent messages in one efficient call."""
        ctx_key = RedisKeys.session_context(session_id)
        msg_key = RedisKeys.session_messages(session_id)
        
        pipe = self._redis.pipeline()
        pipe.hgetall(ctx_key)
        pipe.lrange(msg_key, 0, MAX_MESSAGES - 1)
        results = await pipe.execute()
        
        ctx_data, msg_data = results[0], results[1]
        
        context = None
        if ctx_data:
            try:
                context = SessionContext.from_redis(ctx_data)
            except Exception:
                logger.exception("invalid redis context session_id=%s", session_id)
                
        messages = [json.loads(item) for item in msg_data if item]
        return context, list(reversed(messages))

    async def update_context_fields(self, session_id: str, fields: dict[str, Any]) -> None:
        """Updates specific fields in the session context."""
        key = RedisKeys.session_context(session_id)
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        pipe = self._redis.pipeline()
        pipe.hset(key, mapping=fields)
        pipe.expire(key, TTL.CONTEXT)
        await pipe.execute()

    async def save_message(self, session_id: str, role: str, content: str) -> None:
        """Saves a new message to Redis."""
        key = RedisKeys.session_messages(session_id)
        payload = json.dumps({"role": role, "content": content})
        pipe = self._redis.pipeline()
        pipe.lpush(key, payload)
        pipe.ltrim(key, 0, MAX_MESSAGES - 1)
        pipe.expire(key, TTL.MESSAGES)
        await pipe.execute()

    async def should_summarize(self, session_id: str) -> bool:
        """Checks if it's time to summarize."""
        count_key = RedisKeys.msg_count(session_id)
        count = await self._redis.incr(count_key)
        if count == 1:
            await self._redis.expire(count_key, TTL.MESSAGES)
            return False
        return count % SUMMARIZE_EVERY == 0

    async def reset_counter(self, session_id: str) -> None:
        """Resets the message counter."""
        await self._redis.set(RedisKeys.msg_count(session_id), "0", TTL.MESSAGES)

    async def clear_session(self, session_id: str) -> None:
        """Deletes session data."""
        pipe = self._redis.pipeline()
        pipe.delete(RedisKeys.session_context(session_id), RedisKeys.session_messages(session_id), RedisKeys.msg_count(session_id))
        await pipe.execute()

    async def acquire_summarize_lock(self, session_id: str) -> bool:
        """Acquires a summarization lock."""
        return await self._redis.set_nx(RedisKeys.summarize_lock(session_id), "1", TTL.LOCK)

    async def release_summarize_lock(self, session_id: str) -> None:
        """Releases the summarization lock."""
        await self._redis.delete(RedisKeys.summarize_lock(session_id))

    # --- High-Level Message Lifecycle ---

    async def after_user_message(self, session_id: str | Any, content: str) -> bool:
        """Processes logic after a user message."""
        session_key = str(session_id)
        await self.save_message(session_key, "user", content)
        return await self.should_summarize(session_key)

    async def after_assistant_message(self, session_id: str | Any, content: str, intent: str | None = None) -> None:
        """Processes logic after an assistant message."""
        session_key = str(session_id)
        await self.save_message(session_key, "assistant", content)
        if intent:
            await self.update_context_fields(session_key, {"current_intent": intent})

    async def build_llm_payload(self, session_id: str | Any, user_message: str, max_tokens: int = 3000) -> dict | None:
        """Prepares the payload for the LLM."""
        session_key = str(session_id)
        context, messages = await self.load_session_state(session_key)
        if not context:
            return None

        history = self._truncate_history(messages, max_tokens)
        return {
            "context": context,
            "model": context.model_name,
            "history": history,
            "user_input": user_message,
        }

    def _truncate_history(self, messages: list[dict], max_tokens: int) -> list[dict]:
        """Truncates history based on token estimation."""
        token_count = 0
        trimmed = []
        for msg in reversed(messages):
            est = int(len(msg.get("content", "").split()) * 1.3)
            if token_count + est > max_tokens: break
            trimmed.append(msg)
            token_count += est
        return list(reversed(trimmed))

    async def summarize_current_session(self, session_id: str | Any) -> str | None:
        """Generates and saves a session summary."""
        session_key = str(session_id)
        try:
            _, messages = await self.load_session_state(session_key)
            if not messages: return None
            summary = "\n".join(f"{m['role']}: {m['content'][:120]}" for m in messages[-6:])
            await self.update_context_fields(session_key, {"current_summary": summary})
            await self.reset_counter(session_key)
            return summary
        finally:
            await self.release_summarize_lock(session_key)
