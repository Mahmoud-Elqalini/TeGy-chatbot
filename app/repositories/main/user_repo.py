from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.main.user import MainUser

class MainUserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, user_id: int) -> Optional[MainUser]:
        query = select(MainUser).filter(MainUser.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_source_id(self, user_source_id: str) -> Optional[MainUser]:
        # In main DB, user_source_id might just be the ID or we search by ID
        # For now, assume we can search by some field if needed, or just by ID
        # Based on schema, MainUser has 'id' which is BigInteger
        try:
            int_id = int(user_source_id)
            return await self.get(int_id)
        except ValueError:
            return None

    async def list_for_sync(self, source_ids: set[str] | None = None) -> List[MainUser]:
        query = select(MainUser)
        if source_ids:
            # Convert set of strings to list of ints
            int_ids = [int(sid) for sid in source_ids if sid.isdigit()]
            query = query.filter(MainUser.id.in_(int_ids))
        result = await self.db.execute(query)
        return list(result.scalars().all())
