import time
from app.core.ports.resilience import ResiliencePort
from app.db.redis import RedisClient


class RedisResilienceAdapter(ResiliencePort):
    """
    Distributed Circuit Breaker using Redis.
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def is_circuit_open(self, service_name: str) -> bool:
        circuit_key = f"resilience:circuit:{service_name}:open"
        return await self.redis.exists(circuit_key)

    async def record_failure(self, service_name: str, threshold: int = 5, window: int = 60) -> bool:
        count_key = f"resilience:failures:{service_name}"
        circuit_key = f"resilience:circuit:{service_name}:open"
        
        # Increment failure count
        count = await self.redis.incr(count_key)
        if count == 1:
            await self.redis.expire(count_key, window)
            
        if count >= threshold:
            # 🔴 Open the circuit for 60 seconds
            await self.redis.set(circuit_key, "1", ex=60)
            return True
        return False

    async def record_success(self, service_name: str) -> None:
        count_key = f"resilience:failures:{service_name}"
        circuit_key = f"resilience:circuit:{service_name}:open"
        await self.redis.delete(count_key)
        await self.redis.delete(circuit_key)

    async def allow_probe(self, service_name: str) -> bool:
        """Allows one request to pass through every 10 seconds when circuit is open."""
        probe_key = f"resilience:circuit:{service_name}:probe"
        # If we can set the probe key, it means we are allowed to probe
        return await self.redis.set(probe_key, "1", ex=10, nx=True)
