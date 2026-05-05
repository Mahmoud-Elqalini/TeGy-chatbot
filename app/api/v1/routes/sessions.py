import uuid
from fastapi import APIRouter, Depends, Query, status, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.db_deps import get_chatbot_session
from app.api.v1.auth_deps import get_current_user
from app.core.container import ServiceContainer
from app.schemas.session import SessionRead, PaginatedSessions
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["Sessions"])


# ── Dependency Factory ────────────────────────────────────────────────

async def get_session_service(
    db: AsyncSession = Depends(get_chatbot_session),
) -> SessionService:
    """Delegates assembly to the ServiceContainer (single source of truth)."""
    return await ServiceContainer.build_session_service(db)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedSessions)
async def list_user_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> PaginatedSessions:
    return await service.get_user_sessions(user_id=user_id, skip=skip, limit=limit)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    await service.delete_user_session(session_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from app.schemas.session import SessionUpdate

@router.patch("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_session(
    session_id: uuid.UUID,
    request: SessionUpdate,
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    await service.update_user_session(session_id, user_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
