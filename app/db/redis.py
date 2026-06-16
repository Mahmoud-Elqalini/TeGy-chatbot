from __future__ import annotations

import asyncio
import redis.asyncio as redis
from redis.asyncio.client import Pipeline
from typing import Optional, Any

from app.core.config import settings


# ---------------------------------------------------------------------
# Global Redis singletons (lazy initialization)
# ---------------------------------------------------------------------
_redis_client: Optional[redis.Redis] = None
_redis_wrapper: Optional["RedisClient"] = None
_lock = asyncio.Lock()


# ---------------------------------------------------------------------
# Dependency: Get Redis wrapper (singleton-safe)
# ---------------------------------------------------------------------
async def get_redis() -> "RedisClient":
    """
    Returns a singleton RedisClient instance.

    Thread-safe:
    - Uses asyncio.Lock to avoid multiple initializations
    """
    global _redis_client, _redis_wrapper

    async with _lock:
        if _redis_client is None:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
                ssl=settings.REDIS_SSL,
            )

        if _redis_wrapper is None:
            _redis_wrapper = RedisClient(_redis_client)

    return _redis_wrapper


# ---------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------
async def close_redis() -> None:
    """
    Gracefully close Redis connection.
    Used on application shutdown.
    """
    global _redis_client, _redis_wrapper

    async with _lock:
        if _redis_client:
            await _redis_client.aclose()
            _redis_client = None
            _redis_wrapper = None


# ---------------------------------------------------------------------
# Centralized Redis key management
# ---------------------------------------------------------------------
class RedisKeys:
    """
    Standardized key naming strategy for versioned Redis schema.
    Helps avoid key collisions and improves maintainability.
    """

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




# ---------------------------------------------------------------------
# Redis Client Wrapper (High-level abstraction layer)
# ---------------------------------------------------------------------
class RedisClient:
    """
    Lightweight abstraction over redis.asyncio client.

    Goals:
    - Hide raw Redis API from business logic
    - Add typing safety
    - Centralize common patterns (TTL, JSON, lists, hashes)
    """

    def __init__(self, client: redis.Redis):
        self._r = client

    # -------------------------------------------------------------
    # Basic KV operations
    # -------------------------------------------------------------
    async def get(self, key: str) -> Optional[str]:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._r.setex(key, ttl, value)

    async def set_nx(self, key: str, value: str, ttl: int) -> bool:
        """
        SET if not exists (atomic lock pattern)
        """
        return (await self._r.set(key, value, nx=True, ex=ttl)) is True

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def exists(self, key: str) -> bool:
        return (await self._r.exists(key)) > 0

    async def expire(self, key: str, ttl: int) -> None:
        await self._r.expire(key, ttl)

    async def incr(self, key: str) -> int:
        return await self._r.incr(key)

    async def decrby(self, key: str, amount: int) -> int:
        return await self._r.decrby(key, amount)

    # -------------------------------------------------------------
    # List operations (chat history use-case)
    # -------------------------------------------------------------
    async def lpush(self, key: str, value: str) -> None:
        await self._r.lpush(key, value)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        await self._r.ltrim(key, start, end)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return await self._r.lrange(key, start, end)

    # -------------------------------------------------------------
    # Hash operations
    # -------------------------------------------------------------
    async def hset(
        self,
        key: str,
        field: Optional[str] = None,
        value: Optional[str] = None,
        mapping: Optional[dict[str, Any]] = None,
    ) -> None:
        if mapping is not None:
            await self._r.hset(key, mapping=mapping)
        else:
            await self._r.hset(key, field, value)

    async def hgetall(self, key: str) -> dict:
        return await self._r.hgetall(key)

    # -------------------------------------------------------------
    # System operations
    # -------------------------------------------------------------
    async def ping(self) -> bool:
        return await self._r.ping()

    def pipeline(self) -> Pipeline:
        return self._r.pipeline()

    async def eval(self, script: str, numkeys: int, *args: Any):
        """
        Execute Redis Lua script (used for atomic operations)
        """
        return await self._r.eval(script, numkeys, *args)

    # --------- Cache Management & Cleanup ---------
    async def get_database_info(self) -> dict:
        """Returns detailed database information (size, memory usage)."""
        info = await self._r.info()
        return {
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "keys_total": await self._r.dbsize(),
            "connected_clients": info.get("connected_clients", 0),
            "evicted_keys": info.get("evicted_keys", 0),
        }

    async def get_key_patterns(self, pattern: str = "*") -> list[str]:
        """Scans and returns all keys matching a pattern."""
        keys = []
        async for key in self._r.scan_iter(match=pattern):
            keys.append(key)
        return keys

    async def clear_pattern(self, pattern: str) -> int:
        """Deletes all keys matching a pattern. Returns count deleted."""
        keys = await self.get_key_patterns(pattern)
        if not keys:
            return 0
        
        pipe = self._r.pipeline()
        for key in keys:
            pipe.delete(key)
        results = await pipe.execute()
        return sum(1 for r in results if r > 0)

    async def clear_sessions(self) -> int:
        """Clears all session-related keys (contexts, messages, locks)."""
        session_pattern = f"{RedisKeys.PREFIX}:session:*"
        return await self.clear_pattern(session_pattern)

    async def clear_all_cache(self) -> int:
        """Clears ALL data in the current Redis database. ⚠️ DESTRUCTIVE."""
        count = await self._r.dbsize()
        await self._r.flushdb()
        return count

    async def get_cache_stats(self) -> dict:
        """Returns comprehensive cache statistics."""
        db_info = await self.get_database_info()
        session_keys = await self.get_key_patterns(f"{RedisKeys.PREFIX}:session:*")
        
        # Analyze key types
        key_stats = {}
        for key in session_keys:
            key_type = key.split(":")[2] if len(key.split(":")) > 2 else "unknown"
            key_stats[key_type] = key_stats.get(key_type, 0) + 1
        
        return {
            "database": db_info,
            "session_keys_total": len(session_keys),
            "key_type_breakdown": key_stats,
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }
        