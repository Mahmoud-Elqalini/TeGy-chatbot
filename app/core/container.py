"""
Service Container — Centralised factory for the entire dependency graph.

Design rules:
  1. Each service is constructed in exactly ONE place.
  2. Redis client is resolved once per request scope.
  3. Internal builders are composed via `_build_*` private helpers.
  4. Public API: `build_session_service` and `build_chat_application_service`.
"""
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.intent_detector import IntentDetector
from app.ai.intent_router import IntentRouter
from app.ai.memory_manager import MemoryManager
from app.ai.prompt_builder import PromptBuilder
from app.ai.safety import ResponseValidator
from app.ai.summarizer import Summarizer
from app.db.redis import RedisClient, get_redis
from app.infrastructure.adapters.ai_token_adapter import LLMTokenAdapter
from app.infrastructure.adapters.redis_lock_adapter import RedisLockAdapter
from app.infrastructure.adapters.redis_resilience_adapter import RedisResilienceAdapter
from app.infrastructure.adapters.redis_state_adapter import RedisStateAdapter
from app.repositories.memory_repo import MemoryRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.summary_repo import SummaryRepository
from app.repositories.model_settings_repo import ModelSettingsRepository
from app.services.ai_orchestrator import AIOrchestrator, OrchestratorRuntimeDeps
from app.services.chat_application_service import ChatApplicationService
from app.services.chat_memory_service import ChatMemoryService
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_service import ChatService
from app.services.idempotency_service import IdempotencyService
from app.services.message_service import MessageService
from app.services.session_service import SessionService
from app.services.user_profile_service import UserProfileService


class ServiceContainer:
    """
    Centralised factory that assembles the full dependency graph.
    Each service is constructed in exactly one builder — no duplication.
    """

    # ── Public Builders ───────────────────────────────────────────────

    @staticmethod
    async def build_session_service(db: AsyncSession) -> SessionService:
        """Standalone SessionService for session/history endpoints."""
        redis = await get_redis()
        message_repo = MessageRepository(db)
        return ServiceContainer._build_session_service(db, message_repo, redis)

    @staticmethod
    async def build_chat_application_service(
        request: Request,
        db: AsyncSession,
        main_db: AsyncSession,
    ) -> ChatApplicationService:
        """Fully-wired ChatApplicationService for the chat pipeline."""
        # [DESIGN DECISION]: Fail-fast if Redis is down. 
        # Since Redis is critical for state, locks, and idempotency, we deliberately
        # fail the container build rather than falling back.
        redis = await get_redis()  # Single resolution for entire graph

        # ── Single Construction Point for Repositories ──
        message_repo = MessageRepository(db)

        # ── Shared service (single source of truth) ──
        session_service = ServiceContainer._build_session_service(db, message_repo, redis)

        # ── Infrastructure adapters (all share same redis instance) ──
        state_port = RedisStateAdapter(redis)
        lock_port = RedisLockAdapter(redis)
        resilience_port = RedisResilienceAdapter(redis)
        token_port = LLMTokenAdapter(
            counter=request.app.state.response_generator.count_tokens
        )

        # ── Application workflow services ──
        message_service = MessageService(message_repo)
        persistence = ChatPersistenceService(message_service, session_service)
        memory_workflow = ChatMemoryService(state_port, message_service, request.app.state.arq_pool)
        summarizer = Summarizer(request.app.state.response_generator)

        # db: The Chatbot's internal state DB (sessions, messages, memory).
        # main_db: The primary application DB (events, bookings) passed to tools.
        ai_orchestrator = AIOrchestrator(
            request.app.state.response_generator,
            ResponseValidator(),
            request.app.state.tool_registry,
            runtime_deps=OrchestratorRuntimeDeps(main_db=main_db, db=db)
        )
        chat_domain = ChatService(
            ai_orchestrator=ai_orchestrator,
            intent_detector=IntentDetector(request.app.state.response_generator),
            intent_router=IntentRouter(),
            prompt_builder=PromptBuilder(),
            semantic_cache=request.app.state.semantic_cache,
        )

        # ── Orchestrator assembly ──
        return ChatApplicationService(
            domain=chat_domain,
            token_port=token_port,
            lock_port=lock_port,
            resilience=resilience_port,
            # [DESIGN DECISION]: IdempotencyService takes the raw redis client directly 
            # because its logic is highly Redis-native (TTL, SETNX, binary blobs)
            # and abstracting it behind a port would be an unnecessary leaky abstraction.
            idempotency=IdempotencyService(redis),
            profile_sync=UserProfileService(db, state_port),
            persistence=persistence,
            memory_service=memory_workflow,
            summarizer=summarizer,
        )

    # ── Private Helpers (single construction point per service) ────────

    @staticmethod
    def _build_session_service(db: AsyncSession, message_repo: MessageRepository, redis: RedisClient) -> SessionService:
        """Single construction point for SessionService — used by all builders."""
        return SessionService(
            session_repo=SessionRepository(db),
            message_repo=message_repo,
            # [DESIGN DECISION]: MemoryManager uses raw redis client for native operations
            memory=MemoryManager(redis),
            summary_repo=SummaryRepository(db),
            memory_repo=MemoryRepository(db),
            model_settings_repo=ModelSettingsRepository(db),
        )
