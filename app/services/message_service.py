from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import logging
import uuid


from app.models.chatbot.message import MessageRole
from app.repositories.message_repo import MessageRepository
from app.schemas.message import MessageCreate, MessageRead

logger = logging.getLogger(__name__)


class MessageService:
    def __init__(self, message_repo: MessageRepository):
        self.message_repo = message_repo

    async def save_message(
        self,
        session_id: Union[str, uuid.UUID],
        role: MessageRole,
        content: str,
        metadata: Optional[dict] = None,
        token_count: Optional[int] = None,
    ) -> MessageRead:
        payload = MessageCreate(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
            token_count=token_count if token_count is not None else self._estimate_token_count(content),
        )
        db_obj = await self.message_repo.create(
            {
                "session_id": payload.session_id,
                "role": payload.role,
                "content": payload.content,
                "token_count": payload.token_count,
                "metadata_": payload.metadata,
            }
        )
        return MessageRead.model_validate(db_obj)

    async def get_session_history(self, session_id: Union[str, uuid.UUID], limit: int = 100) -> list:
        return await self.message_repo.get_session_messages(session_id, limit=limit)




    @staticmethod
    def _estimate_token_count(content: str) -> int:
        return max(1, int(len(content.split()) * 1.3)) if content.strip() else 0