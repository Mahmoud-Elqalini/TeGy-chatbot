import json
from typing import Any, Dict
from app.core.ports.state import StatePort
from app.db.redis import RedisClient


class RedisStateAdapter(StatePort):
    """
    Low-level Redis State Adapter.
    Strictly handles byte/json serialization.
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def get_state(self, key: str) -> Any | None:
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def set_state(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.redis.set(key, json.dumps(value), ttl)

    async def delete_state(self, key: str) -> None:
        await self.redis.delete(key)

    async def increment(self, key: str, ttl: int | None = None) -> int:
        new_value = await self.redis.incr(key)
        if ttl:
            await self.redis.expire(key, ttl)
        return new_value

    async def decrement(self, key: str, amount: int) -> int:
        return await self.redis.decrby(key, amount)

    async def set_nx(self, key: str, value: Any, ttl: int | None = None) -> bool:
        success = await self.redis.set_nx(key, json.dumps(value), ttl)
        return success
