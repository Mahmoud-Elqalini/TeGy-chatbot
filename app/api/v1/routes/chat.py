import uuid
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.intent_detector import IntentDetector
from app.ai.intent_router import IntentRouter
from app.ai.memory_manager import MemoryManager
from app.ai.prompt_builder import PromptBuilder
from app.ai.safety import ResponseValidator
from app.api.v1.db_deps import get_chatbot_session
from app.api.v1.auth_deps import get_current_user
from app.core.auth_context import AuthContext, AuthMode
from app.db.redis import get_redis
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.chat_unified import ChatHistoryResponse, ChatMessageRequest, ChatMessageResponse
from app.schemas.session import SessionCreate, SessionRead
from app.services.chat_service import ChatService
from app.services.message_service import MessageService
from app.services.session_service import SessionService
from app.services.ai_orchestrator import AIOrchestrator

router = APIRouter(prefix="/chat", tags=["Chat"])


async def get_chat_dependencies(
    request: Request,
    chatbot_db: AsyncSession = Depends(get_chatbot_session),
) -> dict:
    redis_client = await get_redis()
    memory = MemoryManager(redis_client)

    # Repositories
    session_repo = SessionRepository(chatbot_db)
    message_repo = MessageRepository(chatbot_db)

    # Services
    message_service = MessageService(message_repo)
    session_service = SessionService(session_repo, message_repo, memory)

    # Handlers
    response_generator = request.app.state.response_generator
    intent_detector = IntentDetector(response_generator)
    intent_router = IntentRouter(high_confidence_threshold=0.85, medium_confidence_threshold=0.6)

    # AI Orchestrator
    ai_orchestrator = AIOrchestrator(
        response_generator=response_generator,
        response_validator=ResponseValidator(),
        tool_registry=request.app.state.tool_registry,
        runtime_deps={},
    )

    # Core Chat Service
    chat_service = ChatService(
        ai_orchestrator=ai_orchestrator,
        session_service=session_service,
        message_service=message_service,
        memory=memory,
        intent_detector=intent_detector,
        intent_router=intent_router,
        prompt_builder=PromptBuilder(),
    )

    return {
        "chat_service": chat_service,
        "session_service": session_service,
    }


@router.post("/session", response_model=SessionRead)
async def create_chat_session(
    request: SessionCreate,
    user_id: uuid.UUID = Depends(get_current_user),
    deps: dict = Depends(get_chat_dependencies),
) -> SessionRead:
    # Note: create_session logic is slightly different from get_or_create_session.
    # We'll use the repository-based create since SessionCreate has more fields.
    session_repo = deps["session_service"].session_repo
    session = await session_repo.create({
        "user_id": user_id,
        "channel": request.channel,
        "model_setting_id": request.model_setting_id,
        "title": request.title,
    })
    # Initialize context
    await deps["session_service"].memory.save_context(str(session.session_id), deps["session_service"].memory.load_context(str(session.session_id)) or None) # This is a bit simplified, but create usually doesn't need complex init
    return SessionRead.model_validate(session)


@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(
    request: ChatMessageRequest,
    fastapi_req: Request,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user),
    deps: dict = Depends(get_chat_dependencies),
) -> ChatMessageResponse:
    from app.core.rate_limiter import check_rate_limits
    rl_result = await check_rate_limits(user_id=user_id, ip_address=fastapi_req.client.host, user_tier="free", endpoint="chat")
    
    response.headers["X-RateLimit-Limit"] = str(rl_result.limit)
    response.headers["X-RateLimit-Remaining"] = str(rl_result.remaining)
    response.headers["X-RateLimit-Reset"] = str(rl_result.reset_after)
    
    chat_service: ChatService = deps["chat_service"]
    return await chat_service.send_message(user_id=user_id, request=request)


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    user_id: uuid.UUID = Depends(get_current_user),
    deps: dict = Depends(get_chat_dependencies),
) -> ChatHistoryResponse:
    session_service: SessionService = deps["session_service"]
    return await session_service.get_session_history(session_id=session_id, user_id=user_id, skip=skip, limit=limit)
