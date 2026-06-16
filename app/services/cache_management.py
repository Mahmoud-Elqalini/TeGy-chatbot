"""
Cache Management Service

Centralized management of all caching layers:
- In-memory prompt cache
- Redis session/message cache
- Performance monitoring
- Cleanup and maintenance operations
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.ai.prompt_loader import PromptLoader
from app.db.redis import RedisClient, RedisKeys
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheStats:
    """Data class for cache statistics."""
    
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.redis_stats: Dict[str, Any] = {}
        self.prompt_stats: Dict[str, Any] = {}
        self.summary: Dict[str, Any] = {}


class CacheManager:
    """
    Centralized cache management service.
    
    Handles:
    - Cache cleanup operations
    - Cache statistics gathering
    - Cache warming
    - Performance monitoring
    """
    
    def __init__(self, redis: RedisClient):
        self._redis = redis
    
    # ================================================================
    # PROMPT CACHE MANAGEMENT (In-Memory)
    # ================================================================
    
    def warm_prompt_cache(self) -> Dict[str, str]:
        """
        Loads all prompts into memory cache from disk.
        Called during application startup.
        """
        logger.info("🔥 Warming prompt cache...")
        result = PromptLoader.load_all()
        logger.info(
            f"✅ Prompt cache warmed: {len(result)} prompts loaded",
            extra={"prompt_count": len(result)}
        )
        return result
    
    def clear_prompt_cache(self) -> int:
        """
        Clears the in-memory prompt cache.
        Prompts will be reloaded from disk on next access.
        """
        logger.info("🧹 Clearing prompt cache...")
        PromptLoader.clear_cache()
        logger.info("✅ Prompt cache cleared")
        return len(PromptLoader.cached_names())
    
    def reload_prompt(self, prompt_name: str) -> Optional[str]:
        """
        Hot-reloads a single prompt from disk.
        Useful for admin operations without full restart.
        """
        try:
            content = PromptLoader.hot_reload(prompt_name)
            logger.info(
                f"🔄 Prompt '{prompt_name}' reloaded",
                extra={"prompt_name": prompt_name}
            )
            return content
        except Exception as e:
            logger.error(
                f"❌ Failed to reload prompt '{prompt_name}': {e}",
                extra={"prompt_name": prompt_name, "error": str(e)}
            )
            return None
    
    def get_prompt_cache_info(self) -> Dict[str, Any]:
        """Returns information about the in-memory prompt cache."""
        cached_names = PromptLoader.cached_names()
        return {
            "cached_prompts": cached_names,
            "cache_size": len(cached_names),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    # ================================================================
    # REDIS CACHE MANAGEMENT (Session/Message Cache)
    # ================================================================
    
    async def warm_redis_cache(self) -> Dict[str, Any]:
        """
        Pre-loads critical Redis data.
        Can be extended to load hot sessions, etc.
        """
        logger.info("🔥 Preparing Redis cache...")
        try:
            await self._redis.ping()
            info = await self._redis.get_database_info()
            logger.info(
                "✅ Redis ready",
                extra={"redis_keys": info.get("keys_total", 0)}
            )
            return info
        except Exception as e:
            logger.error(f"❌ Redis cache initialization failed: {e}")
            raise
    
    async def clear_redis_cache(self, scope: str = "sessions") -> Dict[str, Any]:
        """
        Clears Redis cache by scope.
        
        Args:
            scope: One of:
                - "sessions": Clear all session data
                - "all": Clear entire Redis database (⚠️ DESTRUCTIVE)
        
        Returns:
            Dictionary with cleanup statistics
        """
        logger.warning(f"🧹 Clearing Redis cache (scope='{scope}')...")
        
        try:
            if scope == "sessions":
                count = await self._redis.clear_sessions()
                logger.info(
                    f"✅ Cleared {count} session-related keys",
                    extra={"keys_deleted": count, "scope": scope}
                )
                return {"scope": scope, "keys_deleted": count, "status": "success"}
            
            elif scope == "all":
                count = await self._redis.clear_all_cache()
                logger.warning(
                    f"⚠️ Cleared ALL Redis data ({count} keys)",
                    extra={"keys_deleted": count, "scope": scope}
                )
                return {"scope": scope, "keys_deleted": count, "status": "success"}
            
            else:
                logger.error(f"❌ Invalid cache scope: {scope}")
                return {"scope": scope, "keys_deleted": 0, "status": "error", "message": f"Invalid scope: {scope}"}
                
        except Exception as e:
            logger.error(f"❌ Redis cache cleanup failed: {e}")
            return {"scope": scope, "keys_deleted": 0, "status": "error", "message": str(e)}
    
    async def clear_expired_sessions(self, threshold_hours: int = 24) -> Dict[str, Any]:
        """
        Clears expired session data based on TTL.
        Sessions with no activity for >threshold_hours are candidates for cleanup.
        """
        logger.info(f"🧹 Cleaning expired sessions (threshold={threshold_hours}h)...")
        
        try:
            # Redis TTL is handled automatically, so this is mainly for reference
            stats = await self._redis.get_cache_stats()
            logger.info(
                "✅ Expired session cleanup scan completed",
                extra={"stats": stats}
            )
            return {"status": "success", "stats": stats}
        except Exception as e:
            logger.error(f"❌ Expired session cleanup failed: {e}")
            return {"status": "error", "message": str(e)}
    
    # ================================================================
    # CACHE STATISTICS & MONITORING
    # ================================================================
    
    async def get_cache_stats(self) -> CacheStats:
        """
        Gathers comprehensive cache statistics from all layers.
        """
        stats = CacheStats()
        
        # Redis stats
        try:
            stats.redis_stats = await self._redis.get_cache_stats()
        except Exception as e:
            logger.error(f"Failed to gather Redis stats: {e}")
            stats.redis_stats = {"error": str(e)}
        
        # Prompt cache stats
        try:
            stats.prompt_stats = self.get_prompt_cache_info()
        except Exception as e:
            logger.error(f"Failed to gather prompt cache stats: {e}")
            stats.prompt_stats = {"error": str(e)}
        
        # Summary
        stats.summary = {
            "redis_keys": stats.redis_stats.get("database", {}).get("keys_total", 0),
            "cached_prompts": stats.prompt_stats.get("cache_size", 0),
            "redis_memory": stats.redis_stats.get("database", {}).get("used_memory_human", "N/A"),
            "timestamp": stats.timestamp,
        }
        
        return stats
    
    async def get_cache_health(self) -> Dict[str, Any]:
        """
        Returns overall cache health status.
        """
        try:
            stats = await self.get_cache_stats()
            
            # Determine health status
            redis_keys = stats.redis_stats.get("database", {}).get("keys_total", 0)
            prompt_cache_size = stats.prompt_stats.get("cache_size", 0)
            
            # Thresholds (adjust as needed)
            redis_health = "healthy" if redis_keys < 100000 else "degraded"
            prompt_health = "healthy" if prompt_cache_size > 0 else "empty"
            
            return {
                "status": "healthy" if redis_health == "healthy" and prompt_health in ["healthy", "empty"] else "degraded",
                "redis": {
                    "status": redis_health,
                    "keys": redis_keys,
                    "memory": stats.redis_stats.get("database", {}).get("used_memory_human", "N/A"),
                },
                "prompts": {
                    "status": prompt_health,
                    "cached": prompt_cache_size,
                },
                "timestamp": stats.timestamp,
            }
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    # ================================================================
    # CACHE MAINTENANCE
    # ================================================================
    
    async def full_cache_reset(self) -> Dict[str, Any]:
        """
        Performs a full cache reset:
        1. Clears prompt cache
        2. Clears Redis cache
        3. Rewarms prompt cache
        
        ⚠️ DESTRUCTIVE - Use with caution!
        """
        logger.warning("🔄 Performing full cache reset...")
        
        try:
            # Step 1: Clear prompt cache
            prompt_result = self.clear_prompt_cache()
            logger.info(f"Prompt cache cleared")
            
            # Step 2: Clear Redis cache
            redis_result = await self.clear_redis_cache(scope="sessions")
            logger.info(f"Redis cache cleared")
            
            # Step 3: Rewarm prompt cache
            warmed = self.warm_prompt_cache()
            logger.info(f"Prompt cache rewarmed with {len(warmed)} prompts")
            
            return {
                "status": "success",
                "operations": {
                    "prompt_cache_cleared": True,
                    "redis_cache_cleared": True,
                    "redis_keys_deleted": redis_result.get("keys_deleted", 0),
                    "prompt_cache_rewarmed": len(warmed),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ Full cache reset failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
