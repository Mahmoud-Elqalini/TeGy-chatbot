from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from pydantic import BaseModel
import uuid
from app.schemas.message import ChatResponse

from app.api.v1.dependencies import get_db, get_current_user
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.services.message_service import MessageService
from app.services.memory_service import MemoryService
from app.services.llm_service import LLMService
from app.services.session_service import SessionService
from app.services.chat_orchestrator import ChatOrchestrator
from app.ai.memory_manager import MemoryManager
from app.db.redis import get_redis

router = APIRouter(prefix="/chat", tags=["Chat"])

class MessagePayload(BaseModel):
    content: str
    role: str

class ChatRequest(BaseModel):
    session_id: uuid.UUID
    message: MessagePayload

async def get_chat_deps(db: AsyncSession = Depends(get_db)):
    """Yields both the SessionService to verify ownership, and the Orchestrator to execute Chat"""
    redis_client = await get_redis()
    memory_manager = MemoryManager(redis_client)
    memory_service = MemoryService(memory_manager)
    
    message_repo = MessageRepository(db)
    message_service = MessageService(message_repo)
    
    session_repo = SessionRepository(db)
    session_service = SessionService(session_repo, memory_service)
    
    llm_service = LLMService(max_retries=2)
    orchestrator = ChatOrchestrator(message_service, memory_service, llm_service)
    
    return {
        "session_service": session_service,
        "memory_service": memory_service,  # Needed for summarization trigger
        "orchestrator": orchestrator
    }

@router.post("", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user),
    deps: dict = Depends(get_chat_deps)
) -> ChatResponse:
    """
    Core AI Chat Endpoint.
    Takes user content, ensures session authorization, and executes the Orchestrator pipeline.
    Dispatches Summarization to Background Process when signaled.
    """
    session_service: SessionService = deps["session_service"]
    memory_service: MemoryService = deps["memory_service"]
    orchestrator: ChatOrchestrator = deps["orchestrator"]

    # 1. Authorization: Verify session exists and is owned by the incoming JWT token.

    session_id = request.session_id
    session = await session_service.get_session_for_user(session_id, user_id)

    # 2. Execution: Run Orchestrator
    payload = await orchestrator.handle_user_message(session_id=session_id, content=request.message.content)
    
    # 3. Post-Processing: Background tasks dispatching
    # The payload cleanly indicates if we need to summarize
    if payload.should_summarize:
        background_tasks.add_task(memory_service.summarize_session, str(session_id))

    return payload
