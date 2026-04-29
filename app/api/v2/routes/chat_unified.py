import uuid
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.db_deps import get_chatbot_session
from app.api.v1.auth_deps import get_auth_context, get_current_user
from app.db.redis import get_redis
from app.schemas.chat_unified import (
    ChatMessageRequestV2,
    ChatIntegrationResponse,
    ChatMessageResponse,
    ChatHistoryResponse
)
from app.schemas.session import SessionRead, SessionCreate
from app.services.chat_service import ChatService
from app.services.chat_application_service import ChatApplicationService
from app.services.session_service import SessionService
from app.services.message_service import MessageService
from app.services.idempotency_service import IdempotencyService
from app.services.user_profile_service import UserProfileService
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.ai.memory_manager import MemoryManager
from app.ai.intent_detector import IntentDetector
from app.ai.intent_router import IntentRouter
from app.ai.prompt_builder import PromptBuilder
from app.ai.safety import ResponseValidator
from app.services.ai_orchestrator import AIOrchestrator
from app.infrastructure.adapters.redis_state_adapter import RedisStateAdapter
from app.infrastructure.adapters.ai_token_adapter import LLMTokenAdapter
from app.infrastructure.adapters.redis_lock_adapter import RedisLockAdapter
from app.infrastructure.adapters.redis_resilience_adapter import RedisResilienceAdapter
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_memory_service import ChatMemoryService

router = APIRouter(prefix="/chat", tags=["Chat Unified"])


async def get_chat_application_service(
    request: Request,
    db: AsyncSession = Depends(get_chatbot_session)
) -> ChatApplicationService:
    """Dependency that assembles the truly Distributed Cloud-Scale Architecture."""
    redis = await get_redis()
    message_repo = MessageRepository(db)
    session_repo = SessionRepository(db)
    
    # 1. Infrastructure Layer (Adapters - Truly Distributed)
    state_port = RedisStateAdapter(redis)
    lock_port = RedisLockAdapter(redis) 
    resilience_port = RedisResilienceAdapter(redis) # 🔴 Added Distributed Circuit Breaker
    token_port = LLMTokenAdapter(counter=request.app.state.response_generator.count_tokens)
    
    # 2. Application Layer Workflow Services
    message_service = MessageService(message_repo)
    session_service = SessionService(session_repo, message_repo, MemoryManager(redis))
    
    persistence_workflow = ChatPersistenceService(message_service, session_service)
    memory_workflow = ChatMemoryService(state_port)
    
    # 3. Domain Layer
    ai_orchestrator = AIOrchestrator(
        request.app.state.response_generator,
        ResponseValidator(),
        request.app.state.tool_registry,
    )
    
    chat_domain_service = ChatService(
        ai_orchestrator=ai_orchestrator,
        intent_detector=IntentDetector(request.app.state.response_generator),
        intent_router=IntentRouter(),
        prompt_builder=PromptBuilder(),
    )
    
    # 4. Distributed Cloud-Scale Orchestrator
    return ChatApplicationService(
        domain=chat_domain_service,
        token_port=token_port,
        lock_port=lock_port,
        resilience=resilience_port,
        idempotency=IdempotencyService(redis),
        profile_sync=UserProfileService(db),
        persistence=persistence_workflow,
        memory_service=memory_workflow
    )


@router.post("/message", response_model=ChatIntegrationResponse | ChatMessageResponse)
async def send_chat_message(
    request: ChatMessageRequestV2,
    auth = Depends(get_auth_context),
    app_service: ChatApplicationService = Depends(get_chat_application_service),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    """
    Thin Controller: Handles only Auth resolution and delegates to Application Layer.
    """
    return await app_service.execute_chat_flow(
        auth=auth,
        request=request,
        idempotency_key=x_idempotency_key
    )


@router.post("/session", response_model=SessionRead)
async def create_chat_session(
    request: SessionCreate,
    user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_chatbot_session),
):
    session_repo = SessionRepository(db)
    session = await session_repo.create({
        "user_id": user_id,
        "channel": request.channel,
        "model_setting_id": request.model_setting_id,
        "title": request.title,
    })
    return SessionRead.model_validate(session)


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_chatbot_session),
):
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    memory = MemoryManager(await get_redis())
    session_service = SessionService(session_repo, message_repo, memory)
    
    return await session_service.get_session_history(session_id=session_id, user_id=user_id, skip=skip, limit=limit)
