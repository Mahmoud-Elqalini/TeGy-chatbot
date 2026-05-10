from __future__ import annotations
from typing import Optional, Union, List
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc

from app.repositories.base_repo import BaseRepository
from app.models.chatbot.message import Message


class MessageRepository(BaseRepository[Message]):
    def __init__(self, db: AsyncSession):
        super().__init__(Message, db, id_field="message_id")

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Message]:
        return await super().get_all(skip, limit, order_by=asc(self.model.sending_time))

    async def get_session_messages(self, session_id: Union[str, uuid.UUID], skip: int = 0, limit: int = 100) -> List[Message]:
        query = (
            select(self.model)
            .filter(self.model.session_id == session_id)
            .order_by(asc(self.model.sending_time), asc(self.model.message_id))
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_session_messages(self, session_id: Union[str, uuid.UUID]) -> int:
        from sqlalchemy import func
        query = select(func.count(self.model.message_id)).filter(self.model.session_id == session_id)
        result = await self.db.execute(query)
        return result.scalar_one()
