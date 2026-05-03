import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.chatbot.session_memory import SessionMemory
from app.repositories.base_repo import BaseRepository

class MemoryRepository(BaseRepository[SessionMemory]):
    def __init__(self, db: AsyncSession):
        super().__init__(SessionMemory, db, id_field="memory_id")
