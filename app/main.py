import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.core.observability import configure_logging
from app.db.redis import close_redis
from app.api.v1.routes import chat, health, sessions
from app.api.v2.routes import chat_unified

# Import core AI and service components
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.response_generator import ResponseGenerator
from app.ai.tool_registry import ToolRegistry
from app.services.event_service import EventService

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
    
    # 1. Initialize core AI service singletons
    # These will be shared across the entire application for efficiency.
    gemini_provider = GeminiProvider() 
    response_generator = ResponseGenerator(gemini_provider)
    tool_registry = ToolRegistry()
    
    # 2. Register Mock Tools
    # These tools allow the AI to "do things" like fetching events or user profiles.
    # We register them here once at startup so the AI knows how to use them.

    @tool_registry.register(
        name="get_events",
        description="Get a list of available events from the database.",
        parameters={"type": "object", "properties": {}}
    )
    async def get_events(**kwargs):
        """Mock function to simulate fetching events."""
        return [
            {"id": 1, "name": "Tech Conference 2026", "date": "2026-05-15", "location": "Cairo"},
            {"id": 2, "name": "AI Summit", "date": "2026-06-20", "location": "Dubai"}
        ]

    @tool_registry.register(
        name="get_user_profile",
        description="Fetch the current user's profile and settings.",
        parameters={"type": "object", "properties": {}}
    )
    async def get_user_profile(user_id: str | uuid.UUID = "00000000-0000-0000-0000-000000000001", **kwargs):
        """Mock function to simulate getting user data."""
        return {"user_id": str(user_id), "name": "Mock User", "preferences": ["Technology", "AI"]}

    @tool_registry.register(
        name="create_ticket",
        description="Book a ticket for a specific event.",
        parameters={
            "type": "object",
            "properties": {
                "event_id": {"type": "integer", "description": "The unique ID of the event to book."}
            },
            "required": ["event_id"]
        }
    )
    async def create_ticket(event_id: int, **kwargs):
        """Mock function to simulate ticket creation."""
        return {"status": "success", "ticket_id": f"TKT-{event_id}-999", "event_id": event_id}

    @tool_registry.register(
        name="search_orders",
        description="Find all past orders made by the user.",
        parameters={"type": "object", "properties": {}}
    )
    async def search_orders(user_id: str | uuid.UUID = "00000000-0000-0000-0000-000000000001", **kwargs):
        """Mock function to simulate order search."""
        return [{"order_id": 101, "event_id": 1, "status": "confirmed", "amount": 150.0}]
    
    # 3. Save initialized objects to app state
    # This makes them accessible in any route handler via `request.app.state`.
    app.state.gemini_provider = gemini_provider
    app.state.response_generator = response_generator
    app.state.tool_registry = tool_registry
    
    yield
    
    # --- Teardown Phase ---
    # This part runs when the server is shutting down.
    logger.info("Executing safe teardown procedures...")
    await close_redis()
    logger.info("Shutdown complete.")

# Initialize the FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Enterprise API Gateway for AI Chatbot System",
    lifespan=lifespan,
    # Only show API documentation in debug mode for security
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)
app.logger = logger

# Configure CORS (Cross-Origin Resource Sharing)
# This allows browsers to communicate with the API from different domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware to track request context and handle global logic
app.add_middleware(RequestContextMiddleware)

# Register global exception handlers for consistent error responses
register_exception_handlers(app)

# Include API routes from different modules
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(chat_unified.router, prefix="/api/v2")
