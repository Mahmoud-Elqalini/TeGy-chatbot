import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory_manager import MemoryManager
from app.db.redis import get_redis
from app.repositories.session_repo import SessionRepository
from app.repositories.message_repo import MessageRepository
from app.services.session_service import SessionService


async def run_summarization_job(session_id: str | uuid.UUID, chatbot_db: AsyncSession) -> str | None:
    """
    Background job to summarize a chat session and persist it.
    """
    redis_client = await get_redis()
    memory_manager = MemoryManager(redis_client)
    
    # Generate the summary using MemoryManager
    summary = await memory_manager.summarize_current_session(session_id)
    
    if summary is not None:
        # Persist the summary to the database using SessionService
        session_repo = SessionRepository(chatbot_db)
        message_repo = MessageRepository(chatbot_db)
        session_service = SessionService(session_repo, message_repo, memory_manager)
        
        await session_service.finalize_session(
            session_id=uuid.UUID(str(session_id)) if isinstance(session_id, str) else session_id,
            intent="",  # We don't change the intent during summarization
            summary=summary
        )
        
    return summary

