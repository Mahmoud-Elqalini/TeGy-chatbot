from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import SessionNotFoundException
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.summary_repo import SummaryRepository
from app.repositories.memory_repo import MemoryRepository
from app.schemas.session import SessionCreate, SessionRead
from app.schemas.chat_unified import ChatHistoryResponse
from app.schemas.message_schema import ChatMessage
from app.ai.memory_manager import MemoryManager, SessionContext


class SessionService:
    """
    Manages chat sessions, including persistence in DB and sync with Redis memory.
    """
    def __init__(
        self, 
        session_repo: SessionRepository, 
        message_repo: MessageRepository, 
        memory: MemoryManager,
        summary_repo: SummaryRepository | None = None,
        memory_repo: MemoryRepository | None = None
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.memory = memory
        self.summary_repo = summary_repo
        self.memory_repo = memory_repo

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

    async def finalize_session(self, session_id: uuid.UUID, intent: str, summary: str | dict | None = None):
        """Updates session metadata in the database."""
        session = await self.session_repo.get(session_id)
        if not session: return
        
        updates = {
            "last_active": datetime.now(timezone.utc),
            "current_intent": intent
        }
        
        # Handle if summary is a dictionary from the new AI summarizer
        if isinstance(summary, dict):
            await self.update_summarization_results(session_id, summary)
            updates["current_summary"] = summary.get("session_summary")
        elif summary:
            updates["current_summary"] = summary
            
        await self.session_repo.update(session, updates)

    async def update_summarization_results(self, session_id: uuid.UUID, summary_data: dict):
        """
        Stores advanced summarization results into versioned conv_summaries
        and session_memory tables.
        """
        if not self.summary_repo or not self.memory_repo:
            return

        # 1. Store Versioned Summary
        latest_version = await self.summary_repo.get_latest_version(session_id)
        await self.summary_repo.create({
            "session_id": session_id,
            "summary": summary_data.get("conv_summary") or summary_data.get("session_summary"),
            "version": latest_version + 1
        })

        # 2. Store Key Points in Session Memory
        key_points = summary_data.get("key_points", [])
        for point in key_points:
            await self.memory_repo.create({
                "session_id": session_id,
                "memory_type": "key_point",
                "content": point,
                "importance": 0.8
            })

    async def get_session_history(self, session_id: uuid.UUID, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> ChatHistoryResponse:
        """Fetches session metadata and paginated messages."""
        session = await self.get_session_model_for_user(session_id, user_id)
        messages = await self.message_repo.get_session_messages(session_id, skip=skip, limit=limit)
        typed_messages = [ChatMessage.model_validate(m) for m in messages]
        return ChatHistoryResponse(
            session_id=session.session_id,
            messages=typed_messages
        )

    async def get_user_sessions(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> list[SessionRead]:
        sessions = await self.session_repo.get_user_sessions(user_id, skip, limit)
        return [SessionRead.model_validate(s) for s in sessions]

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        try:
            return await self.session_repo.delete(session_id)
        finally:
            await self.memory.clear_session(str(session_id))
