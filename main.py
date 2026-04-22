import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.db.redis import close_redis
from app.api.v1.routes import auth, sessions, chat

# Setup standard logging natively
# logging.basicConfig(
#     level=logging.INFO if not settings.DEBUG else logging.DEBUG,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
# )
logging.basicConfig(
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle event manager for the FastAPI application.
    Executes startup logic before receiving requests, and teardown logic on termination.
    """
    logger.info("Initializing Enterprise Backend AI Framework...")
    # SQL Engine and Redis Pools are lazily initialized, but if specific boot checks
    # are required, they can be awaited here.
    
    yield
    
    logger.info("Executing safe teardown procedures...")
    # Safely drain the Redis connection pool to prevent hanging sockets
    await close_redis()
    logger.info("Shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Enterprise API Gateway for AI Chatbot System",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

# 1. Register security & cross-origin limits
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in Production to strict origins
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Register Global Exception Handlers securely mapping exact Domain boundaries
register_exception_handlers(app)

# 3. Mount fully decoupled Routing modules
# (Each router autonomously manages its own dependency injection bounds)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")

@app.get("/health", tags=["System"])
async def health_check():
    """Returns the operational status of the gateway."""
    return {"status": "ok", "version": "1.0.0"}
