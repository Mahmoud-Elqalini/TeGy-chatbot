import uuid
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.db_deps import get_chatbot_session
from app.api.v1.auth_deps import get_auth_context, get_current_user
from app.core.container import ServiceContainer
from app.db.redis import get_redis
from app.schemas.chat_unified import (
    ChatMessageRequest,
    ChatIntegrationResponse,
    ChatMessageResponse,
    ChatHistoryResponse
)
from app.schemas.session import SessionRead, SessionCreate
from app.services.chat_application_service import ChatApplicationService
from app.services.session_service import SessionService
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.ai.memory_manager import MemoryManager

router = APIRouter(prefix="/chat", tags=["Chat"])


async def get_chat_application_service(
    request: Request,
    db: AsyncSession = Depends(get_chatbot_session)
) -> ChatApplicationService:
    """Delegates assembly to the ServiceContainer."""
    return await ServiceContainer.build_chat_application_service(request, db)



@router.post("/message", response_model=ChatIntegrationResponse | ChatMessageResponse)
async def send_chat_message(
    request: ChatMessageRequest,
    auth = Depends(get_auth_context),
    app_service: ChatApplicationService = Depends(get_chat_application_service),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    """
    Thin Controller: Handles only Auth resolution and delegates to Application Layer.
    """
    return await app_service.execute(
        auth=auth,
        api_request=request,
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
