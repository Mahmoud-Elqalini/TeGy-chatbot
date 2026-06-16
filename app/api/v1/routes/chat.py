from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
from fastapi import APIRouter, Depends, Header, Request, Response, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.db_deps import get_chatbot_session, get_main_session
from app.api.v1.auth_deps import get_auth_context, get_current_user
from app.core.container import ServiceContainer
from app.schemas.chat_unified import (
    ChatMessageRequest,
    ChatIntegrationResponse,
    ChatMessageResponse,
    ChatHistoryResponse
)
from app.schemas.session import SessionRead, SessionCreate
from app.services.chat_application_service import ChatApplicationService
from app.services.session_service import SessionService

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Dependency Factories ──────────────────────────────────────────────

async def get_chat_application_service(
    request: Request,
    db: AsyncSession = Depends(get_chatbot_session),
    main_db: AsyncSession = Depends(get_main_session)
) -> ChatApplicationService:
    """Delegates assembly to the ServiceContainer."""
    return await ServiceContainer.build_chat_application_service(request, db, main_db)


async def get_session_service(
    db: AsyncSession = Depends(get_chatbot_session),
) -> SessionService:
    """Delegates assembly to the ServiceContainer."""
    return await ServiceContainer.build_session_service(db)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/message", response_model=Union[ChatIntegrationResponse, ChatMessageResponse])
async def send_chat_message(
    request: ChatMessageRequest,
    background_tasks: BackgroundTasks,
    auth = Depends(get_auth_context),
    app_service: ChatApplicationService = Depends(get_chat_application_service),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Thin Controller: Handles only Auth resolution and delegates to Application Layer.
    """
    return await app_service.execute(
        auth=auth,
        api_request=request,
        idempotency_key=x_idempotency_key,
        background_tasks=background_tasks
    )


@router.post("/session", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    request: SessionCreate,
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    """Creates a session in PostgreSQL and initializes its context in Redis."""
    session = await service.create_session(request, user_id)
    return SessionRead.model_validate(session)


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    """Returns paginated message history for a session owned by the caller."""
    return await service.get_session_history(
        session_id=session_id, user_id=user_id, skip=skip, limit=limit
    )
