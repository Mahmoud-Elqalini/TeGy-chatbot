import uuid
from typing import List, Optional
from app.repositories.session_repo import SessionRepository
from app.schemas.session import SessionCreate, SessionUpdate, SessionRead
from app.services.memory_service import MemoryService
import logging

logger = logging.getLogger(__name__)

class SessionService:
    def __init__(self, session_repo: SessionRepository, memory_service: MemoryService):
        self.session_repo = session_repo
        self.memory_service = memory_service

    async def create_session(self, session_in: SessionCreate, user_id: uuid.UUID) -> SessionRead:
        obj_in = session_in.model_dump()
        obj_in["user_id"] = user_id
        db_obj = await self.session_repo.create(obj_in)
        return SessionRead.model_validate(db_obj)

    async def get_user_sessions(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[SessionRead]:
        db_objs = await self.session_repo.get_user_sessions(user_id=user_id, skip=skip, limit=limit)
        return [SessionRead.model_validate(obj) for obj in db_objs]

    async def get_session(self, session_id: uuid.UUID) -> Optional[SessionRead]:
        db_obj = await self.session_repo.get(session_id)
        if not db_obj:
            return None
        return SessionRead.model_validate(db_obj)

    async def get_session_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionRead:
        from fastapi import HTTPException, status
        session = await self.get_session(session_id)
        if not session or session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or not accessible.")
        return session

    async def update_session(self, session_id: uuid.UUID, session_in: SessionUpdate) -> Optional[SessionRead]:
        db_obj = await self.session_repo.get(session_id)
        if not db_obj:
            return None
        updated_obj = await self.session_repo.update(db_obj, session_in.model_dump(exclude_unset=True))
        return SessionRead.model_validate(updated_obj)

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        """
        Deletes a session from the persistent DB.
        Ensures Redis is cleared regardless of DB failure.
        """
        try:
            # Delete from DB
            deleted = await self.session_repo.delete(session_id)
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete session {session_id} from DB: {e}")
            raise
        finally:
            # Clear Redis memory regardless of whether DB deletion succeeds or throws an exception.
            await self.memory_service.end_session(str(session_id))
