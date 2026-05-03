"""
Service Container — Factory for assembling the ChatApplicationService dependency graph.
Replaces the "monster dependency" function that was in the route file.
"""
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.intent_detector import IntentDetector
from app.ai.intent_router import IntentRouter
from app.ai.memory_manager import MemoryManager
from app.ai.prompt_builder import PromptBuilder
from app.ai.safety import ResponseValidator
from app.db.redis import get_redis
from app.infrastructure.adapters.ai_token_adapter import LLMTokenAdapter
from app.infrastructure.adapters.redis_lock_adapter import RedisLockAdapter
from app.infrastructure.adapters.redis_resilience_adapter import RedisResilienceAdapter
from app.infrastructure.adapters.redis_state_adapter import RedisStateAdapter
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.services.ai_orchestrator import AIOrchestrator
from app.services.chat_application_service import ChatApplicationService
from app.services.chat_memory_service import ChatMemoryService
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_service import ChatService
from app.services.idempotency_service import IdempotencyService
from app.services.message_service import MessageService
from app.services.session_service import SessionService
from app.services.user_profile_service import UserProfileService
from app.ai.summarizer import Summarizer
from app.repositories.summary_repo import SummaryRepository
from app.repositories.memory_repo import MemoryRepository


class ServiceContainer:
    """
    Centralised factory that assembles the full dependency graph
    for the ChatApplicationService.
    """

    @staticmethod
    async def build_chat_application_service(
        request: Request,
        db: AsyncSession,
    ) -> ChatApplicationService:
        """
        Build and return a fully-wired ChatApplicationService instance.
        """
        redis = await get_redis()
        message_repo = MessageRepository(db)
        session_repo = SessionRepository(db)

        # 1. Infrastructure Layer (Adapters)
        state_port = RedisStateAdapter(redis)
        lock_port = RedisLockAdapter(redis)
        resilience_port = RedisResilienceAdapter(redis)
        token_port = LLMTokenAdapter(counter=request.app.state.response_generator.count_tokens)

        # 2. Application Layer Workflow Services
        message_service = MessageService(message_repo)
        session_service = SessionService(
            session_repo, 
            message_repo, 
            MemoryManager(redis),
            summary_repo=SummaryRepository(db),
            memory_repo=MemoryRepository(db)
        )

        persistence_workflow = ChatPersistenceService(message_service, session_service)
        memory_workflow = ChatMemoryService(state_port)
        summarizer = Summarizer(request.app.state.response_generator)

        # 3. Domain Layer
        ai_orchestrator = AIOrchestrator(
            request.app.state.response_generator,
            ResponseValidator(),
            request.app.state.tool_registry,
        )

        chat_domain_service = ChatService(
            ai_orchestrator=ai_orchestrator,
            intent_detector=IntentDetector(request.app.state.response_generator),
            intent_router=IntentRouter(),
            prompt_builder=PromptBuilder(),
        )

        # 4. Orchestrator Assembly
        return ChatApplicationService(
            domain=chat_domain_service,
            token_port=token_port,
            lock_port=lock_port,
            resilience=resilience_port,
            idempotency=IdempotencyService(redis),
            profile_sync=UserProfileService(db),
            persistence=persistence_workflow,
            memory_service=memory_workflow,
            summarizer=summarizer,
        )
