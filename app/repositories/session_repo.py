from typing import List
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chatbot.session import Session
from app.repositories.base_repo import BaseRepository


class SessionRepository(BaseRepository[Session]):
    def __init__(self, db: AsyncSession):
        super().__init__(Session, db, id_field="session_id")

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Session]:
        return await super().get_all(skip, limit, order_by=desc(self.model.last_active))

    async def get_user_sessions(self, user_id: str | uuid.UUID, skip: int = 0, limit: int = 100) -> List[Session]:
        query = (
            select(self.model)
            .filter(self.model.user_id == user_id)
            .order_by(desc(self.model.last_active))
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_owned_session(self, session_id: str | uuid.UUID, user_id: str | uuid.UUID) -> Session | None:
        query = select(self.model).filter(self.model.session_id == session_id, self.model.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
