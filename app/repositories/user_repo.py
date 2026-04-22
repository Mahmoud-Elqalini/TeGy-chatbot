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

    async def get_by_name(self, name: str) -> Optional[User]:
        query = select(self.model).filter(self.model.name == name)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        query = select(self.model).filter(self.model.email == email)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
