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
        session_id: str | uuid.UUID,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
        token_count: int | None = None,
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



    @staticmethod
    def _estimate_token_count(content: str) -> int:
        return max(1, int(len(content.split()) * 1.3)) if content.strip() else 0
