import uuid
from typing import List
from app.repositories.message_repo import MessageRepository
from app.schemas.message import MessageCreate, MessageRead, MessageStatusEnum, MessageRoleEnum
from app.core.exceptions import MessageNotFoundException, AppException

class MessageService:
    def __init__(self, message_repo: MessageRepository):
        self.message_repo = message_repo

    async def save_message(self, session_id: uuid.UUID, role: MessageRoleEnum, content: str, status: MessageStatusEnum = MessageStatusEnum.completed) -> MessageRead:
        msg_in = MessageCreate(session_id=session_id, role=role, content=content, status=status)
        db_obj = await self.message_repo.create(msg_in.model_dump())
        return MessageRead.model_validate(db_obj)

    async def finalize_message(self, message_id: uuid.UUID, status: MessageStatusEnum, content: str = None) -> MessageRead:
        db_obj = await self.message_repo.get(message_id)
        if not db_obj:
            raise MessageNotFoundException(f"Message {message_id} not found")
        
        update_data = {"status": status}
        if content is not None:
            update_data["content"] = content
            
        updated_obj = await self.message_repo.update(db_obj, update_data)
        if updated_obj is None:
            # Domain exception if underlying DB update fails without throwing its own exception
            raise AppException(status_code=500, detail=f"Failed to cleanly apply updates to Message {message_id}")

        return MessageRead.model_validate(updated_obj)

    async def get_session_messages(self, session_id: uuid.UUID, skip: int = 0, limit: int = 50) -> List[MessageRead]:
        db_objs = await self.message_repo.get_session_messages(session_id=session_id, skip=skip, limit=limit)
        return [MessageRead.model_validate(obj) for obj in db_objs]
