from typing import Optional, List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.repositories.base_repo import BaseRepository
from app.models.conv_summary import ConvSummary

class SummaryRepository(BaseRepository[ConvSummary]):
    def __init__(self, db: AsyncSession):
        super().__init__(ConvSummary, db, id_field="summarize_id")

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ConvSummary]:
        return await super().get_all(skip, limit, order_by=desc(self.model.created_at))

    async def get_latest_summary(self, session_id: uuid.UUID) -> Optional[ConvSummary]:
        # Ordering by version first, then created_at to avoid ties if multiple summaries hit
        query = select(self.model).filter(self.model.session_id == session_id).order_by(desc(self.model.version), desc(self.model.created_at)).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
