from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import SessionNotFoundException
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.session import SessionCreate, SessionRead, SessionUpdate
from app.schemas.chat_unified import ChatHistoryResponse
from app.ai.memory_manager import MemoryManager, SessionContext

logger = logging.getLogger(__name__)


class SessionService:
    """
    Manages chat sessions, including persistence in DB and sync with Redis memory.
    """
    def __init__(self, session_repo: SessionRepository, message_repo: MessageRepository, memory: MemoryManager):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.memory = memory

    async def get_or_create_session(self, session_id: uuid.UUID | None, user_id: uuid.UUID) -> Any:
        """Ensures a session exists and is initialized in memory."""
        if session_id:
            session = await self.get_session_model_for_user(session_id, user_id)
        else:
            session = await self.create_session(SessionCreate(title="New Chat"), user_id)
            return session # create_session already handles memory sync

        # Sync with Redis memory if needed
        existing_ctx = await self.memory.load_context(str(session.session_id))
        if not existing_ctx:
            context = SessionContext(
                session_id=str(session.session_id),
                user_id=str(session.user_id),
                channel=session.channel or "web",
                current_intent=session.current_intent or "",
                current_summary=session.current_summary or "",
            )
            await self.memory.save_context(str(session.session_id), context)
            
        return session

    async def create_session(self, session_in: SessionCreate, user_id: uuid.UUID) -> Any:
        """Creates a new session in DB and initializes memory."""
        session = await self.session_repo.create({
            "user_id": user_id,
            "title": session_in.title,
            "channel": session_in.channel or "web",
            "model_setting_id": session_in.model_setting_id
        })
        context = SessionContext(
            session_id=str(session.session_id),
            user_id=str(session.user_id),
            channel=session.channel or "web",
            system_prompt=session_in.system_prompt or ""
        )
        await self.memory.save_context(str(session.session_id), context)
        return session

    async def get_session_model_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        """Fetches a session and validates ownership."""
        session = await self.session_repo.get_owned_session(session_id, user_id)
        if not session:
            raise SessionNotFoundException("Session not found or inaccessible.")
        return session

    async def finalize_session(self, session_id: uuid.UUID, intent: str, summary: str | None = None):
        """Updates session metadata in the database."""
        session = await self.session_repo.get(session_id)
        if not session: return
        
        updates = {
            "last_active": datetime.now(timezone.utc),
            "current_intent": intent
        }
        if summary:
            updates["current_summary"] = summary
            
        await self.session_repo.update(session, updates)

    async def get_session_history(self, session_id: uuid.UUID, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> ChatHistoryResponse:
        """Fetches session metadata and paginated messages."""
        session = await self.get_session_model_for_user(session_id, user_id)
        messages = await self.message_repo.get_session_messages(session_id, skip=skip, limit=limit)
        return ChatHistoryResponse(
            session=SessionRead.model_validate(session),
            messages=messages
        )

    async def get_user_sessions(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> list[SessionRead]:
        sessions = await self.session_repo.get_user_sessions(user_id, skip, limit)
        return [SessionRead.model_validate(s) for s in sessions]

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        try:
            return await self.session_repo.delete(session_id)
        finally:
            await self.memory.clear_session(str(session_id))
