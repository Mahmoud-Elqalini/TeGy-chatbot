import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.chatbot.session_summary import ConvSummary
from app.repositories.base_repo import BaseRepository

class SummaryRepository(BaseRepository[ConvSummary]):
    def __init__(self, db: AsyncSession):
        super().__init__(ConvSummary, db, id_field="summarize_id")

    async def get_latest_version(self, session_id: uuid.UUID) -> int:
        query = select(func.max(self.model.version)).filter(self.model.session_id == session_id)
        result = await self.db.execute(query)
        return result.scalar() or 0
