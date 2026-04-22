from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.api.v1.dependencies import get_db, get_current_user
from app.repositories.session_repo import SessionRepository
from app.services.session_service import SessionService
from app.services.memory_service import MemoryService
from app.ai.memory_manager import MemoryManager
from app.db.redis import get_redis
from app.schemas.session import SessionCreate, SessionRead

router = APIRouter(prefix="/sessions", tags=["Sessions"])

async def get_session_service(db: AsyncSession = Depends(get_db)):
    """Dependency injector for SessionService"""
    session_repo = SessionRepository(db)
    redis_client = await get_redis()
    memory_manager = MemoryManager(redis_client)
    memory_service = MemoryService(memory_manager)
    return SessionService(session_repo, memory_service)

@router.get("", response_model=List[SessionRead])
async def list_user_sessions(
    skip: int = 0,
    limit: int = 50,
    user_id: uuid.UUID = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Retrieves the history of sessions for the currently authenticated user.
    """
    return await session_service.get_user_sessions(user_id=user_id, skip=skip, limit=limit)

@router.post("", response_model=SessionRead)
async def create_session(
    session_in: SessionCreate,
    user_id: uuid.UUID = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Creates a new chat session natively linked to the authenticated token.
    Throws 403 HTTP Exception implicitly if token fails, but creates securely otherwise.
    """
    return await session_service.create_session(session_in, user_id)

@router.delete("/{session_id}", response_model=dict)
async def delete_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Deletes the session securely from MySQL and strictly purges it from Redis memory.
    """
    # Verify ownership before deletion to prevent IDOR attacks.
    session = await session_service.get_session_for_user(session_id, user_id)
        
    await session_service.delete_session(session_id)
    return {"status": "success", "message": f"Session {session_id} successfully deleted from Database and Memory."}
