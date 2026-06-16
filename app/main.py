import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.core.observability import configure_logging
from app.db.redis import close_redis, get_redis
from app.api.v1.routes import chat, health, sessions

# Import core AI and service components
from app.ai.response_generator import ResponseGenerator
from app.ai.tool_registry import ToolRegistry
from app.ai.tools import discover_and_register
from app.ai.prompt_loader import PromptLoader
from app.services.cache_management import CacheManager
from arq import create_pool
from app.workers.arq_jobs import get_arq_redis_settings

# Configure the logging system based on the debug setting
configure_logging(bool(settings.DEBUG))
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles the application's lifecycle events.
    This function runs once when the server starts and once when it stops.
    It's used to initialize and clean up shared resources.
    """
    logger.info("Initializing Enterprise Backend AI Infrastructure...")
    
    # --- Initialization Phase ---
    
    # Initialize the provider fallback chain (Groq -> Fireworks -> Gemini)
    # automatically based on configuration and priority.
    from app.ai.providers.factory import ProviderFactory
    primary_provider = ProviderFactory.initialize_provider_chain()

    # 1. Initialize response generator
    response_generator = ResponseGenerator(primary_provider)
    
    # 2. Auto-discover and register all tools from app/ai/tools/
    # This must happen BEFORE ToolRegistry() to populate the global catalog.
    discover_and_register()
    
    # 3. Initialize cache manager for centralized cache operations
    redis_client = await get_redis()
    cache_manager = CacheManager(redis_client)
    
    # 4. Warm the cache (loads all .md/.txt files from app/ai/prompts/ and validates Redis)
    try:
        cache_manager.warm_prompt_cache()
        await cache_manager.warm_redis_cache()
        logger.info("✅ Cache warming completed successfully")
    except Exception as e:
        logger.warning(f"⚠️ Cache warming encountered issues: {e}")
    
    # 5. Initialize tool registry (clones the global catalog)
    tool_registry = ToolRegistry()
    
    # 6. Save initialized objects to app state
    # This makes them accessible in any route handler via `request.app.state`.
    app.state.ai_provider = primary_provider
    app.state.response_generator = response_generator
    app.state.tool_registry = tool_registry
    app.state.arq_pool = await create_pool(get_arq_redis_settings())
    app.state.cache_manager = cache_manager
    
    logger.info("✅ Application startup completed")
    
    yield
    
    # --- Teardown Phase ---
    # This part runs when the server is shutting down.
    logger.info("Executing safe teardown procedures...")
    
    # 1. Log cache statistics before shutdown
    try:
        cache_stats = await cache_manager.get_cache_stats()
        logger.info(
            "Cache statistics before shutdown",
            extra={
                "redis_keys": cache_stats.redis_stats.get("database", {}).get("keys_total"),
                "cached_prompts": cache_stats.prompt_stats.get("cache_size"),
            }
        )
    except Exception as e:
        logger.warning(f"Failed to gather cache stats: {e}")
    
    # 2. Close AI provider resources (httpx clients, etc.)
    try:
        await primary_provider.close()
        logger.info("✅ AI provider resources closed")
    except Exception as e:
        logger.error(f"Error closing AI provider: {e}")
    
    # 3. Log final provider metrics for observability
    if hasattr(primary_provider, "get_metrics_summary"):
        try:
            for m in primary_provider.get_metrics_summary():
                logger.info("provider.metrics.final", extra=m)
        except Exception as e:
            logger.warning(f"Failed to log provider metrics: {e}")
    
    # 4. Close ARQ pool
    if hasattr(app.state, "arq_pool"):
        try:
            await app.state.arq_pool.close()
            logger.info("✅ ARQ pool closed")
        except Exception as e:
            logger.error(f"Error closing ARQ pool: {e}")
    
    # 5. Close Redis connection (final cleanup)
    try:
        await close_redis()
        logger.info("✅ Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")
    
    logger.info("✅ Shutdown complete")


# OpenAPI Tags for API documentation
openapi_tags = [
    {"name": "Chat", "description": "Chat messaging endpoints"},
    {"name": "Sessions", "description": "Session management endpoints"},
    {"name": "System", "description": "Health checks and system status"},
]

# Initialize the FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.API_VERSION,
    description="Enterprise API Gateway for AI Chatbot System",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
    # Only show API documentation in debug mode for security
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)
app.logger = logger

# Configure CORS (Cross-Origin Resource Sharing)
# This allows browsers to communicate with the API from different domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware to track request context and handle global logic
app.add_middleware(RequestContextMiddleware)

# Register global exception handlers for consistent error responses
register_exception_handlers(app)

# Include API routes from different modules
app.include_router(chat.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
