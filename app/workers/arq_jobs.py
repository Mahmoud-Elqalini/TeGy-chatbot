from __future__ import annotations
import uuid

try:
    from arq import Retry  # type: ignore
    from arq.connections import RedisSettings, create_pool  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class Retry(Exception):
        def __init__(self, defer: int = 0):
            self.defer = defer

    class RedisSettings:  # type: ignore
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    async def create_pool(*args, **kwargs):  # type: ignore
        raise RuntimeError("ARQ is not installed.")

from app.core.config import settings
from app.db.chatbot_database import ChatbotSessionLocal
from app.workers.summarization_worker import run_summarization_job
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.fallback_provider import FallbackProvider
from app.ai.response_generator import ResponseGenerator
from app.core.observability import get_logger

logger = get_logger(__name__)

async def startup(ctx: dict):
    logger.info("Worker starting up... Initializing AI Providers.")
    # Initialize basic provider chain for the worker
    providers = [GeminiProvider()]
    if settings.GROQ_API_KEY:
        from app.ai.providers.groq_provider import GroqProvider
        providers.append(GroqProvider())
    if settings.OPENROUTER_API_KEY:
        from app.ai.providers.openrouter_provider import OpenRouterProvider
        providers.append(OpenRouterProvider())
        
    primary_provider = FallbackProvider(providers) if len(providers) > 1 else providers[0]
    ctx["response_generator"] = ResponseGenerator(primary_provider)
    ctx["primary_provider"] = primary_provider

async def shutdown(ctx: dict):
    logger.info("Worker shutting down...")
    provider = ctx.get("primary_provider")
    if provider:
        await provider.close()


def get_arq_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.ARQ_REDIS_SETTINGS_HOST,
        port=settings.ARQ_REDIS_SETTINGS_PORT,
        database=settings.ARQ_REDIS_SETTINGS_DB,
        password=settings.ARQ_REDIS_SETTINGS_PASSWORD or None,
    )


# Removed _persist_failed_job as FailedJob model was deleted in schema simplification.


async def summarize_session_job(ctx: dict, session_id: str | uuid.UUID, message_count: int) -> str | None:
    try:
        response_generator = ctx["response_generator"]
        async with ChatbotSessionLocal() as chatbot_db:
            return await run_summarization_job(session_id, message_count, chatbot_db, response_generator)
    except Exception as exc:
        retries = ctx.get("job_try", 1)
        if retries < settings.ARQ_MAX_RETRIES:
            raise Retry(defer=(2 ** retries))
        logger.error("worker.summarize.failed", session_id=str(session_id), retries=retries, error=str(exc))
        raise


class WorkerSettings:
    redis_settings = get_arq_redis_settings()
    functions = [summarize_session_job]
    queue_name = settings.ARQ_QUEUE_NAME
    max_jobs = 10
    job_timeout = settings.ARQ_JOB_TIMEOUT_SECONDS
    on_startup = startup
    on_shutdown = shutdown


async def queue_health() -> dict:
    try:
        pool = await create_pool(get_arq_redis_settings())
    except Exception as exc:
        return {"queue": "unavailable", "error": str(exc)}
    info = await pool.info()
    await pool.close()
    return {"queue": "ok", "redis_version": info.get("redis_version")}
