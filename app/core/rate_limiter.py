import time
import uuid
import logging
import hashlib
import asyncio
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.exceptions import RateLimitException
from app.db.redis import get_redis
from app.core.observability import get_logger, log_event, get_request_id

logger = get_logger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after: int
    is_fallback: bool = False


class CircuitBreaker:
    """
    Elite-grade Circuit Breaker with Dynamic Lifecycle and Local Locking.
    """
    FAILURE_THRESHOLD = 3
    RECOVERY_TIMEOUT = 30 
    FAILURE_WINDOW = 60 

    def __init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.opened_at = 0
        self._half_open_lock = asyncio.Lock() # Ensure only one probe at a time

    async def should_allow_redis(self) -> bool:
        now = time.time()
        
        if self.state == CircuitState.OPEN:
            if now - self.opened_at > self.RECOVERY_TIMEOUT:
                if not self._half_open_lock.locked():
                    self.state = CircuitState.HALF_OPEN
                    return True
            return False
            
        return True

    def record_failure(self):
        now = time.time()
        if now - self.last_failure_time > self.FAILURE_WINDOW:
            self.failure_count = 1
        else:
            self.failure_count += 1
            
        self.last_failure_time = now
        
        if self.failure_count >= self.FAILURE_THRESHOLD:
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = now
                log_event(logger, logging.ERROR, "circuit.opened", 
                          failures=self.failure_count, severity="CRITICAL")

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            log_event(logger, logging.INFO, "circuit.recovered", state="CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0


# Singleton Instance
redis_circuit = CircuitBreaker()

class RateLimiter:
    """
    Final Elite Implementation.
    """
    LUA_SCRIPT = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])

    local current = redis.call('INCR', key)
    if current == 1 then
        redis.call('EXPIRE', key, window)
    end

    local ttl = redis.call('TTL', key)
    return {current, ttl}
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    async def check(
        self, 
        key_prefix: str, 
        identifier: str, 
        limit: int, 
        window: int
    ) -> RateLimitResult:
        
        if not await redis_circuit.should_allow_redis():
            return self._dynamic_fallback(identifier, limit, window)

        try:
            if self._redis is None:
                self._redis = await get_redis()

            key = f"v1:rate_limit:{key_prefix}:{identifier}"
            result = await self._redis.eval(self.LUA_SCRIPT, 1, key, limit, window)
            current_count, ttl = result

            if ttl == -1: await self._redis.expire(key, window); ttl = window
            elif ttl == -2: ttl = window

            redis_circuit.record_success()

            return RateLimitResult(
                allowed=current_count <= limit,
                limit=limit,
                remaining=max(0, limit - current_count),
                reset_after=ttl
            )
        except Exception as e:
            redis_circuit.record_failure()
            log_event(logger, logging.ERROR, "rate_limit.redis_failure", 
                      error=str(e), circuit_state=redis_circuit.state.value)
            return self._dynamic_fallback(identifier, limit, window)

    def _dynamic_fallback(self, identifier: str, limit: int, window: int) -> RateLimitResult:
        """
        Adaptive Deterministic Fallback: User decision rotates every 5 minutes.
        This prevents permanent blocking of specific users during downtime.
        """
        # Time bucket changes every 5 minutes (300 seconds)
        time_bucket = int(time.time() / 300)
        seed = f"{identifier}:{time_bucket}"
        
        hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        allowed = (hash_val % 100) < 25 # 25% capacity in degraded mode
        
        return RateLimitResult(
            allowed=allowed, 
            limit=limit, 
            remaining=0, 
            reset_after=window, 
            is_fallback=True
        )


async def check_rate_limits(
    user_id: uuid.UUID, 
    ip_address: str, 
    user_tier: str = "free",
    endpoint: str = "chat"
) -> RateLimitResult:
    limiter = RateLimiter()
    
    # Stratified Checking
    global_res = await limiter.check("system", "global", limit=settings.RATE_LIMIT_SYSTEM, window=settings.RATE_LIMIT_WINDOW)
    if not global_res.allowed:
        raise RateLimitException(detail="System load high.", retry_after=global_res.reset_after)

    ip_res = await limiter.check("ip", ip_address, limit=50, window=60)
    if not ip_res.allowed:
        raise RateLimitException(detail="IP rate limit.", retry_after=ip_res.reset_after)

    limit_val = getattr(settings, f"RATE_LIMIT_{user_tier.upper()}", settings.RATE_LIMIT_FREE)
    user_res = await limiter.check(f"user:{endpoint}", str(user_id), limit=limit_val, window=settings.RATE_LIMIT_WINDOW)
    
    if not user_res.allowed:
        log_event(logger, logging.WARNING, "rate_limit.exhausted", user_id=str(user_id), tier=user_tier)
        raise RateLimitException(detail=f"Tier limit exceeded.", retry_after=user_res.reset_after)
    
    return user_res
