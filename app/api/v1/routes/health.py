from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.db_deps import get_chatbot_session, get_main_session
from app.core.config import settings
from app.db.redis import get_redis
from app.services.cache_management import CacheManager
from app.workers import queue_health

router = APIRouter(prefix="/health", tags=["System"])


@router.get("", summary="Health Check")
async def health_check(
    chatbot_db: AsyncSession = Depends(get_chatbot_session),
    main_db: AsyncSession = Depends(get_main_session),
):
    health_status = {
        "status": "ok",
        "version": "1.0.0",
        "environment": "development" if settings.DEBUG else "production",
        "databases": {"chatbot": "ok", "main": "ok"},
        "redis": "ok",
        "queue": "ok",
    }

    # Check Chatbot DB
    try:
        await chatbot_db.execute(text("SELECT 1"))
    except Exception as e:
        health_status["databases"]["chatbot"] = f"error: {str(e)}"
        health_status["status"] = "error"

    # Check Main DB
    try:
        await main_db.execute(text("SELECT 1"))
    except Exception as e:
        health_status["databases"]["main"] = f"error: {str(e)}"
        health_status["status"] = "error"

    # Check Redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "error"

    # Check Queue (arq)
    try:
        health_status["queue"] = await queue_health()
    except Exception as e:
        health_status["queue"] = f"error: {str(e)}"
        health_status["status"] = "error"

    return health_status


# ================================================================
# CACHE MANAGEMENT ENDPOINTS
# ================================================================

@router.get("/cache/status", summary="Cache Status & Statistics")
async def get_cache_status(redis: object = Depends(get_redis)):
    """
    Returns comprehensive cache statistics and status.
    Includes Redis memory usage, session count, and prompt cache info.
    """
    cache_manager = CacheManager(redis)
    stats = await cache_manager.get_cache_stats()
    
    return {
        "status": "ok",
        "cache": {
            "redis": stats.redis_stats,
            "prompts": stats.prompt_stats,
            "summary": stats.summary,
        },
        "timestamp": stats.timestamp,
    }


@router.get("/cache/health", summary="Cache Health Check")
async def get_cache_health(redis: object = Depends(get_redis)):
    """
    Returns overall cache health status.
    Checks Redis memory, prompt cache availability, and key thresholds.
    """
    cache_manager = CacheManager(redis)
    health = await cache_manager.get_cache_health()
    return health


@router.post("/cache/clear/sessions", summary="Clear Session Cache")
async def clear_session_cache(redis: object = Depends(get_redis)):
    """
    Clears all session-related Redis data.
    ⚠️ This will clear all active sessions and their messages!
    """
    cache_manager = CacheManager(redis)
    result = await cache_manager.clear_redis_cache(scope="sessions")
    
    return {
        "status": result.get("status"),
        "message": f"Cleared {result.get('keys_deleted', 0)} session-related keys",
        "details": result,
    }


@router.post("/cache/clear/prompts", summary="Clear Prompt Cache")
async def clear_prompt_cache():
    """
    Clears the in-memory prompt cache.
    Prompts will be reloaded from disk on next access.
    """
    try:
        result = CacheManager(None).clear_prompt_cache()
        return {
            "status": "ok",
            "message": "Prompt cache cleared",
            "prompts_cleared": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


@router.post("/cache/warm", summary="Warm Cache")
async def warm_cache(redis: object = Depends(get_redis)):
    """
    Pre-loads all cached data into memory.
    - Loads prompts from disk
    - Initializes Redis connection
    """
    try:
        cache_manager = CacheManager(redis)
        
        # Warm prompt cache
        prompts = cache_manager.warm_prompt_cache()
        
        # Check Redis
        redis_info = await cache_manager.warm_redis_cache()
        
        return {
            "status": "ok",
            "message": "Cache warming completed",
            "operations": {
                "prompts_loaded": len(prompts),
                "redis_keys": redis_info.get("keys_total", 0),
                "redis_memory": redis_info.get("used_memory_human", "N/A"),
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Cache warming failed: {str(e)}",
        }


@router.post("/cache/reset", summary="Full Cache Reset")
async def full_cache_reset(redis: object = Depends(get_redis)):
    """
    Performs a complete cache reset:
    1. Clears prompt cache
    2. Clears Redis session cache
    3. Rewarms prompt cache
    
    ⚠️ DESTRUCTIVE - This will clear all active sessions!
    """
    try:
        cache_manager = CacheManager(redis)
        result = await cache_manager.full_cache_reset()
        
        return {
            "status": result.get("status"),
            "message": "Full cache reset completed",
            "operations": result.get("operations"),
            "timestamp": result.get("timestamp"),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Cache reset failed: {str(e)}",
        }


@router.post("/cache/reload-prompt/{prompt_name}", summary="Reload Single Prompt")
async def reload_single_prompt(prompt_name: str):
    """
    Hot-reloads a single prompt from disk without full cache reset.
    Useful for testing prompt changes without restarting the server.
    """
    try:
        cache_manager = CacheManager(None)
        content = cache_manager.reload_prompt(prompt_name)
        
        if content is None:
            return {
                "status": "error",
                "message": f"Prompt '{prompt_name}' not found",
            }
        
        return {
            "status": "ok",
            "message": f"Prompt '{prompt_name}' reloaded",
            "prompt_name": prompt_name,
            "content_length": len(content),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }

