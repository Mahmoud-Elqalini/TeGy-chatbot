from __future__ import annotations
from typing import Union, Optional, Any, List, Dict

import json
from app.db.redis import RedisClient


# ---------------------------------------------------------------------
# Lua Script (Atomic Idempotency Control)
# ---------------------------------------------------------------------
# Ensures full atomic behavior inside Redis:
#
# 1. If result already exists → return cached result (status = 1)
# 2. If lock exists → another request is processing (status = 2)
# 3. Otherwise → acquire lock and allow processing (status = 0)
# ---------------------------------------------------------------------
_IDEMPOTENCY_LUA = """
local result_key = KEYS[1]
local lock_key   = KEYS[2]

-- Check cached response first
local cached = redis.call('GET', result_key)
if cached then
    return {1, cached}
end

-- Try to acquire lock (NX = only if not exists)
local locked = redis.call('SET', lock_key, '1', 'NX', 'EX', 30)
if not locked then
    return {2, nil}
end

-- No cache and lock acquired → proceed
return {0, nil}
"""


# ---------------------------------------------------------------------
# Idempotency Service
# ---------------------------------------------------------------------
class IdempotencyService:
    """
    Handles request deduplication using Redis-based idempotency keys.

    Behavior:
    - Prevents duplicate processing of the same request
    - Ensures safe retries in distributed systems
    - Guarantees single execution per idempotency key
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis

    # -------------------------------------------------------------
    # Key helpers
    # -------------------------------------------------------------
    def _keys(self, idempotency_key: str) -> tuple[str, str]:
        """
        Generate Redis keys for:
        - Cached result
        - Processing lock
        """
        return (
            f"idem:{idempotency_key}",
            f"idem_lock:{idempotency_key}",
        )

    # -------------------------------------------------------------
    # Check idempotency state
    # -------------------------------------------------------------
    async def check(self, idempotency_key: str) -> tuple[str, Optional[dict]]:
        """
        Check current request state.

        Returns:
            - "hit"     → cached result exists (return immediately)
            - "locked"  → request is already being processed
            - "proceed" → safe to process request
        """

        result_key, lock_key = self._keys(idempotency_key)

        status, data = await self.redis.eval(
            _IDEMPOTENCY_LUA,
            2,
            result_key,
            lock_key,
        )

        if status == 1:
            return "hit", json.loads(data)

        if status == 2:
            return "locked", None

        return "proceed", None

    # -------------------------------------------------------------
    # Simple cache read (used by ChatApplicationService)
    # -------------------------------------------------------------
    async def get(self, idempotency_key: str) -> Optional[dict]:
        """
        Returns the cached result for *idempotency_key*, or None if not cached.
        This is the lightweight read-only variant used before entering the pipeline.
        """
        result_key, _ = self._keys(idempotency_key)
        raw = await self.redis.get(result_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------
    # Save result after successful processing
    # -------------------------------------------------------------
    async def save(self, idempotency_key: str, result: dict) -> None:
        """
        Store result in Redis and release lock.

        TTL:
            24 hours (86400 seconds)
        """

        result_key, lock_key = self._keys(idempotency_key)

        await self.redis.set(
            result_key,
            json.dumps(result),
            ttl=86400,
        )

        await self.redis.delete(lock_key)