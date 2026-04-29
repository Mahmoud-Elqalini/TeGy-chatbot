from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.main.event import Event

class MainEventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_source_id(self, event_source_id: int) -> Optional[Event]:
        query = select(Event).filter(Event.event_source_id == event_source_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def search_events(self, query: str, limit: int = 5) -> list[Event]:
        stmt = (
            select(Event)
            .filter(Event.name.ilike(f"%{query}%"), Event.is_deleted.is_(False))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
