import uuid
from typing import Any, Dict
from app.services.message_service import MessageService
from app.services.session_service import SessionService
from app.models.chatbot.message import MessageRole


class ChatPersistenceService:
    """
    Generic Chat Persistence Service.
    Does NOT know about 'intent', 'route', or AI internals.
    Operates on roles, content, and generic metadata.
    """

    def __init__(self, message_service: MessageService, session_service: SessionService):
        self.message_service = message_service
        self.session_service = session_service

    async def save_message(
        self, 
        session_id: uuid.UUID, 
        role: str, 
        content: str, 
        tokens: int, 
        metadata: Dict[str, Any] | None = None
    ) -> None:
        """Saves a message with generic metadata."""
        await self.message_service.save_message(
            session_id=session_id,
            role=role,
            content=content,
            token_count=tokens,
            metadata=metadata
        )

    async def finalize_session(self, session_id: uuid.UUID, metadata: Dict[str, Any] | None = None, version: int | None = None) -> None:
        """Finalizes session using metadata blob."""
        # Map metadata to expected fields if necessary, but keep service interface generic
        intent = metadata.get("intent", "unknown") if metadata else "unknown"
        summary = metadata.get("summary") if metadata else None
        await self.session_service.finalize_session(session_id, intent, summary, version=version)
