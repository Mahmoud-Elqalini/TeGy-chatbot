from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.db_deps import get_chatbot_session, get_main_session
from app.core.config import settings
from app.db.redis import get_redis
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
