from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.repositories.base_repo import BaseRepository
from app.models.user import User

class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db, id_field="user_id")

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        return await super().get_all(skip, limit, order_by=desc(self.model.created_at))
