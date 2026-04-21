from __future__ import annotations
import json
import logging
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, field_validator
from app.db.redis import RedisClient, RedisKeys

logger = logging.getLogger(__name__)


class TTL:
    MESSAGES = 60 * 60 * 24
    CONTEXT  = 60 * 60 * 24 * 7
    SUMMARY  = 60 * 60 * 24 * 30
    LOCK     = 300


MAX_MESSAGES    = 20
SUMMARIZE_EVERY = 10


class SessionContext(BaseModel):
    user_id:         str
    title:           str
    current_intent:  str = ""
    current_summary: str = ""
    model_name:      str = ""
    system_prompt:   str = ""
    updated_at:      str = ""
    version:         int = 0

    @field_validator("user_id", "title")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> SessionContext:
        return cls(
            user_id         = data.get("user_id", ""),
            title           = data.get("title", ""),
            current_intent  = data.get("current_intent", ""),
            current_summary = data.get("current_summary", ""),
            model_name      = data.get("model_name", ""),
            system_prompt   = data.get("system_prompt", ""),
            updated_at      = data.get("updated_at", ""),
            version         = int(data.get("version", 0)),
        )

    def to_redis(self) -> dict[str, str]:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.version   += 1
        return {
            "user_id":         self.user_id,
            "title":           self.title,
            "current_intent":  self.current_intent,
            "current_summary": self.current_summary,
            "model_name":      self.model_name,
            "system_prompt":   self.system_prompt,
            "updated_at":      self.updated_at,
            "version":         str(self.version),
        }


class MemoryManager:
    def __init__(self, redis: RedisClient):
        self._r = redis

    async def load_context(self, session_id: str) -> Optional[SessionContext]:
        key  = RedisKeys.session_context(session_id)
        data = await self._r.hgetall(key)
        if not data:
            return None
        try:
            return SessionContext.from_redis(data)
        except Exception:
            logger.error("invalid context schema for session %s", session_id)
            return None

    async def save_context(self, session_id: str, context: SessionContext) -> None:
        key  = RedisKeys.session_context(session_id)
        pipe = self._r.pipeline()
        pipe.hset(key, mapping=context.to_redis())
        pipe.expire(key, TTL.CONTEXT)
        await pipe.execute()

    async def load_messages(self, session_id: str) -> list[dict]:
        key      = RedisKeys.session_messages(session_id)
        raw      = await self._r.lrange(key, 0, MAX_MESSAGES - 1)
        messages = []
        for m in raw:
            try:
                messages.append(json.loads(m))
            except json.JSONDecodeError:
                logger.error(
                    "corrupted message in session %s: %r",
                    session_id, m,
                )
                continue
        return messages

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        msg_key = RedisKeys.session_messages(session_id)
        message = json.dumps({"role": role, "content": content})
        pipe    = self._r.pipeline()
        pipe.lpush(msg_key, message)
        pipe.ltrim(msg_key, 0, MAX_MESSAGES - 1)
        pipe.expire(msg_key, TTL.MESSAGES)
        await pipe.execute()

    async def should_summarize(self, session_id: str) -> bool:
        count_key = RedisKeys.msg_count(session_id)
        count     = await self._r.incr(count_key)
        if count == 1:
            await self._r.expire(count_key, TTL.MESSAGES)
            return False
        return count % SUMMARIZE_EVERY == 0

    async def reset_counter(self, session_id: str) -> None:
        count_key = RedisKeys.msg_count(session_id)
        await self._r.set(count_key, "0", TTL.MESSAGES)

    async def update_intent(self, session_id: str, intent: str) -> None:
        key  = RedisKeys.session_context(session_id)
        pipe = self._r.pipeline()
        pipe.hset(key, "current_intent", intent)
        pipe.hset(key, "updated_at", datetime.now(timezone.utc).isoformat())
        pipe.expire(key, TTL.CONTEXT)
        await pipe.execute()

    async def update_summary(self, session_id: str, summary: str) -> None:
        key  = RedisKeys.session_context(session_id)
        pipe = self._r.pipeline()
        pipe.hset(key, "current_summary", summary)
        pipe.hset(key, "updated_at", datetime.now(timezone.utc).isoformat())
        pipe.expire(key, TTL.SUMMARY)
        await pipe.execute()

    async def clear_session(self, session_id: str) -> None:
        pipe = self._r.pipeline()
        pipe.delete(RedisKeys.session_context(session_id))
        pipe.delete(RedisKeys.session_messages(session_id))
        pipe.delete(RedisKeys.msg_count(session_id))
        await pipe.execute()

    async def acquire_summarize_lock(self, session_id: str) -> bool:
        key = RedisKeys.summarize_lock(session_id)
        return await self._r.set_nx(key, "1", TTL.LOCK)

    async def release_summarize_lock(self, session_id: str) -> None:
        key = RedisKeys.summarize_lock(session_id)
        await self._r.delete(key)
        logger.info("released summarize lock for session %s", session_id)