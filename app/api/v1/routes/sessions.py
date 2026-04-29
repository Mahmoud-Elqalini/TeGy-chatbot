import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory_manager import MemoryManager
from app.api.v1.db_deps import get_chatbot_session
from app.api.v1.auth_deps import get_current_user
from app.db.redis import get_redis
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.session import SessionRead
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["Sessions"])


async def get_session_service(db: AsyncSession = Depends(get_chatbot_session)) -> SessionService:
    redis_client = await get_redis()
    memory = MemoryManager(redis_client)
    return SessionService(SessionRepository(db), MessageRepository(db), memory)


@router.get("", response_model=list[SessionRead])
async def list_user_sessions(
    skip: int = 0,
    limit: int = 50,
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> list[SessionRead]:
    return await service.get_user_sessions(user_id=user_id, skip=skip, limit=limit)


@router.delete("/{session_id}", response_model=dict)
async def delete_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> dict:
    await service.get_session_model_for_user(session_id, user_id)
    await service.delete_session(session_id)
    return {"status": "success", "message": f"Session {session_id} deleted."}
