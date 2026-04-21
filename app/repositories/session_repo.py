from typing import List, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.repositories.base_repo import BaseRepository
from app.models.session import Session

class SessionRepository(BaseRepository[Session]):
    def __init__(self, db: AsyncSession):
        super().__init__(Session, db, id_field="session_id")

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Session]:
        return await super().get_all(skip, limit, order_by=desc(self.model.last_active))

    async def get_user_sessions(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[Session]:
        query = select(self.model).filter(self.model.user_id == user_id).order_by(desc(self.model.last_active)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())
