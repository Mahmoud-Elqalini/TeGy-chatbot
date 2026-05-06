from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import logging

from app.core.config import settings
from app.core.exceptions import SessionNotFoundException, ModelSettingsNotFoundException, ValidationException
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.summary_repo import SummaryRepository
from app.repositories.memory_repo import MemoryRepository
from app.repositories.model_settings_repo import ModelSettingsRepository
from app.schemas.session import SessionCreate, SessionRead, SessionListRead, PaginatedSessions, SessionUpdate
from app.schemas.chat_unified import ChatHistoryResponse
from app.schemas.message_schema import ChatMessage
from app.ai.memory_manager import MemoryManager, SessionContext

logger = logging.getLogger(__name__)


class SessionService:
    """
    Manages chat sessions, including persistence in DB and sync with Redis memory.
    """
    def __init__(
        self, 
        session_repo: SessionRepository, 
        message_repo: MessageRepository, 
        memory: MemoryManager,
        model_settings_repo: ModelSettingsRepository,
        summary_repo: SummaryRepository | None = None,
        memory_repo: MemoryRepository | None = None
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.memory = memory
        self.summary_repo = summary_repo
        self.memory_repo = memory_repo
        self.model_settings_repo = model_settings_repo

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
                system_prompt=session.system_prompt or settings.DEFAULT_SYSTEM_PROMPT
            )
            try:
                await self.memory.save_context(str(session.session_id), context)
            except Exception as e:
                logger.warning(f"Failed to sync session context to Redis: {e}")
            
        return session

    async def create_session(self, session_in: SessionCreate, user_id: uuid.UUID) -> Any:
        """Creates a new session in DB and initializes memory."""
        if not user_id:
            raise ValidationException("user_id cannot be null")

        system_prompt = await self._resolve_system_prompt(session_in)

        session = await self.session_repo.create({
            "user_id": user_id,
            "title": session_in.title,
            "channel": session_in.channel or "web",
            "model_setting_id": session_in.model_setting_id,
            "system_prompt": system_prompt
        })
        
        context = SessionContext(
            session_id=str(session.session_id),
            user_id=str(session.user_id),
            channel=session.channel or "web",
            system_prompt=system_prompt
        )
        try:
            await self.memory.save_context(str(session.session_id), context)
        except Exception as e:
            logger.warning(f"Redis cache save failed for session {session.session_id}, continuing anyway. Error: {e}")
        return session

    async def _resolve_system_prompt(self, session_in: SessionCreate) -> str:
        """Resolves the system prompt strictly from the global configuration."""
        logger.info("system_prompt.resolved", extra={"source": "config_default"})
        return settings.DEFAULT_SYSTEM_PROMPT

    async def get_session_model_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        """Fetches a session and validates ownership."""
        session = await self.session_repo.get_owned_session(session_id, user_id)
        if not session:
            raise SessionNotFoundException("Session not found or inaccessible.")
        return session

    async def finalize_session(self, session_id: uuid.UUID, intent: str, summary: str | dict | None = None, version: int | None = None):
        """Updates session metadata in the database."""
        session = await self.session_repo.get(session_id)
        if not session: return
        
        updates = {
            "last_active": datetime.now(timezone.utc),
            "current_intent": intent
        }
        
        # Handle if summary is a dictionary from the new AI summarizer
        if isinstance(summary, dict):
            await self.update_summarization_results(session_id, summary, target_version=version)
            updates["current_summary"] = summary.get("session_summary")
        elif summary:
            updates["current_summary"] = summary
            
        await self.session_repo.update(session, updates)

    async def update_summarization_results(self, session_id: uuid.UUID, summary_data: dict, target_version: int | None = None):
        """
        Stores advanced summarization results into versioned conv_summaries
        and session_memory tables.
        """
        if not self.summary_repo or not self.memory_repo:
            return

        # 1. Store Versioned Summary
        version = target_version
        if version is None:
            latest_version = await self.summary_repo.get_latest_version(session_id)
            version = latest_version + 1
            
        await self.summary_repo.create({
            "session_id": session_id,
            "summary": summary_data.get("conv_summary") or summary_data.get("session_summary"),
            "version": version
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
        
        # Parallel fetch for performance
        import asyncio
        total_task = self.message_repo.count_session_messages(session_id)
        messages_task = self.message_repo.get_session_messages(session_id, skip=skip, limit=limit)
        total, messages = await asyncio.gather(total_task, messages_task)
        
        typed_messages = [ChatMessage.model_validate(m) for m in messages]
        return ChatHistoryResponse(
            session_id=session.session_id,
            messages=typed_messages,
            total=total,
            skip=skip,
            limit=limit
        )

    async def get_user_sessions(self, user_id: uuid.UUID, skip: int, limit: int) -> PaginatedSessions:
        total = await self.session_repo.count_user_sessions(user_id)
        sessions = await self.session_repo.get_user_sessions(user_id, skip, limit)
        items = [SessionListRead.model_validate(s) for s in sessions]
        return PaginatedSessions(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )

    async def delete_user_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Atomically deletes a user session from DB and memory."""
        success = await self.session_repo.delete_user_session(session_id, user_id)
        if not success:
            raise SessionNotFoundException("Session not found or inaccessible.")
        
        # Only clear memory if DB deletion was successful
        await self.memory.clear_session(str(session_id))

    async def update_user_session(self, session_id: uuid.UUID, user_id: uuid.UUID, update_schema: SessionUpdate) -> None:
        """Atomically updates a user session."""
        update_data = update_schema.model_dump(exclude_unset=True)
        if not update_data:
            return
            
        success = await self.session_repo.update_user_session(session_id, user_id, update_data)
        if not success:
            raise SessionNotFoundException("Session not found or inaccessible.")
