from __future__ import annotations
import asyncio
import redis.asyncio as redis
from redis.asyncio.client import Pipeline
from typing import Optional
from app.core.config import settings


_redis_client: Optional[redis.Redis] = None
_redis_wrapper: Optional[RedisClient] = None
_lock = asyncio.Lock()


async def get_redis() -> RedisClient:
    global _redis_client, _redis_wrapper
    async with _lock:
        if _redis_client is None:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
            )
        if _redis_wrapper is None:
            _redis_wrapper = RedisClient(_redis_client)
    return _redis_wrapper


async def close_redis() -> None:
    global _redis_client, _redis_wrapper
    async with _lock:
        if _redis_client:
            await _redis_client.aclose()
            _redis_client = None
            _redis_wrapper = None


class RedisKeys:
    PREFIX = "v1"

    @classmethod
    def session_context(cls, session_id: str) -> str:
        return f"{cls.PREFIX}:session:{session_id}:context"

    @classmethod
    def session_messages(cls, session_id: str) -> str:
        return f"{cls.PREFIX}:session:{session_id}:messages"

    @classmethod
    def msg_count(cls, session_id: str) -> str:
        return f"{cls.PREFIX}:session:{session_id}:msg_count"

    @classmethod
    def summarize_lock(cls, session_id: str) -> str:
        return f"{cls.PREFIX}:session:{session_id}:summarizing"

    @classmethod
    def user_active_session(cls, user_id: str) -> str:
        return f"{cls.PREFIX}:user:{user_id}:active_session"

    @classmethod
    def user_requests(cls, user_id: str) -> str:
        return f"{cls.PREFIX}:user:{user_id}:requests"


class RedisClient:
    def __init__(self, client: redis.Redis):
        self._r = client

    async def get(self, key: str) -> Optional[str]:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._r.setex(key, ttl, value)

    async def set_nx(self, key: str, value: str, ttl: int) -> bool:
        result = await self._r.set(key, value, nx=True, ex=ttl)
        return result is True

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def lpush(self, key: str, value: str) -> None:
        await self._r.lpush(key, value)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        await self._r.ltrim(key, start, end)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return await self._r.lrange(key, start, end)

    async def expire(self, key: str, ttl: int) -> None:
        await self._r.expire(key, ttl)

    async def exists(self, key: str) -> bool:
        return (await self._r.exists(key)) > 0

    async def incr(self, key: str) -> int:
        return await self._r.incr(key)

    async def hset(
        self,
        key: str,
        field: Optional[str] = None,
        value: Optional[str] = None,
        mapping: Optional[dict] = None,
    ) -> None:
        if mapping:
            await self._r.hset(key, mapping=mapping)
        else:
            await self._r.hset(key, field, value)

    async def hgetall(self, key: str) -> dict:
        return await self._r.hgetall(key)

    def pipeline(self) -> Pipeline:
        return self._r.pipeline()