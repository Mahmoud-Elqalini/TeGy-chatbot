from __future__ import annotations
from typing import Union, Optional
import uuid
import logging
import time
import asyncio

from app.core.perf_tracer import PerformanceTracer
from fastapi import HTTPException, BackgroundTasks
from app.core.exceptions import AppException

from app.core.config import settings

from app.core.auth_context import AuthContext
from app.core.ports.tokens import TokenPort
from app.core.ports.lock import LockPort
from app.core.ports.resilience import ResiliencePort
from app.schemas.chat_unified import (
    ChatMessageRequest,
    ChatIntegrationResponse,
    ChatMessageResponse,
    ChatMessageMetadata
)
from app.schemas.chat_dtos import ChatDomainRequest, ChatDomainResponse, WorkflowContext, ChatContext
from app.ai.fast_path_router import FastPathRouter
from app.services.chat_service import ChatService
from app.services.idempotency_service import IdempotencyService
from app.services.user_profile_service import UserProfileService
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_memory_service import ChatMemoryService
from app.ai.summarizer import Summarizer

from app.db.chatbot_database import ChatbotSessionLocal
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository

logger = logging.getLogger(__name__)


class ChatApplicationService:
    """
    Truly Distributed Production Orchestrator.
    Features: Atomic Safe Locks, Distributed Circuit Breaker, 
    Structured Logging, and Exponential Backoff.
    """

    def __init__(
        self,
        domain: ChatService,
        token_port: TokenPort,
        lock_port: LockPort,
        resilience: ResiliencePort,
        idempotency: IdempotencyService,
        profile_sync: UserProfileService,
        persistence: ChatPersistenceService,
        memory_service: ChatMemoryService,
        summarizer: Summarizer,
        fast_path_router: Optional[FastPathRouter] = None,
    ):
        self.domain = domain
        self.tokens = token_port
        self.lock = lock_port
        self.resilience = resilience
        self.idempotency = idempotency
        self.profile = profile_sync
        self.persistence = persistence
        self.memory = memory_service
        self.summarizer = summarizer
        self.fast_path = fast_path_router or FastPathRouter()

    async def execute(
        self,
        auth: AuthContext,
        api_request: ChatMessageRequest,
        idempotency_key: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Union[ChatIntegrationResponse, ChatMessageResponse]:
        """
        Resilient Distributed Pipeline.

        Guarantees:
          1. Persistence via background lock-transfer for both fast path and normal path,
             guaranteeing strict message ordering without blocking the response.
          2. Fallback (failed AI generation) persistence is always inline for reliability.
          3. Assistant response is saved only on successful generation.
          4. On AI failure, a fallback assistant message is saved inline with status='failed_generation'.
          5. Idempotency is strictly serialized per session to prevent race conditions.

        Token-based identity: user_id is ALWAYS resolved from AuthContext.
        """
        request_id = str(uuid.uuid4())
        tracer = PerformanceTracer()

        # ── Identity Resolution (Single Source of Truth: Token) ──
        ctx = WorkflowContext(
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            auth_mode=auth.mode,
            start_time=time.time()
        )

        log_meta = {"request_id": request_id, "user_id": str(ctx.user_id), "session_id": str(api_request.session_id)}
        logger.info("pipeline_start", extra=log_meta)

        # Circuit Breaker Check
        if await self.resilience.is_circuit_open("ai_service"):
            if not await self.resilience.allow_probe("ai_service"):
                logger.error("circuit_breaker_open", extra=log_meta)
                raise HTTPException(status_code=503, detail="Service unavailable")

        # ── Acquire Lock FIRST ──
        # This serializes Idempotency checks and Fast Path execution to prevent race conditions.
        session_key = str(api_request.session_id or ctx.user_id)
        # Ensure TTL is comfortably longer than the AI timeout so it doesn't expire mid-generation
        lock_token = await self.lock.acquire(session_key, ttl=settings.AI_REQUEST_TIMEOUT + 30)
        if not lock_token:
            logger.warning("concurrency_lock_failed", extra=log_meta)
            raise HTTPException(status_code=429, detail="Concurrent request in progress.")

        release_lock = True
        try:
            # ── Idempotency Check (Safely protected by lock) ──
            if idempotency_key:
                cached_response = await self.idempotency.get(idempotency_key)
                if cached_response:
                    logger.info("idempotency_hit", extra={"request_id": request_id, "idempotency_key": idempotency_key})
                    if auth.mode == "INTEGRATION":
                        return ChatIntegrationResponse.model_validate(cached_response)
                    return ChatMessageResponse.model_validate(cached_response)

            # ── ZERO-CONTEXT FAST PATH CHECK ──
            fast_path_result = self.fast_path.match(api_request.message)
            if fast_path_result is not None:
                logger.info("fast_path.zero_context_hit", extra=log_meta)
                res_content = fast_path_result.response
                
                # Pre-generate session_id for new chats so we can return it instantly
                if api_request.session_id is None:
                    api_request.session_id = uuid.uuid4()
                
                # To maintain both latency and strict message ordering, we execute the
                # persistence in a background task but we DO NOT release the lock here.
                # The lock is transferred to the background task and released upon completion.
                if background_tasks:
                    background_tasks.add_task(
                        self._fast_path_background_finalize,
                        ctx, api_request, res_content, fast_path_result.fast_path_type,
                        session_key, lock_token
                    )
                    release_lock = False
                else:
                    # Fallback to inline if background_tasks is not provided
                    await self._fast_path_finalize(ctx, api_request, res_content, fast_path_result.fast_path_type)
                    
                try:
                    if ctx.auth_mode == "INTEGRATION":
                        response = ChatIntegrationResponse(response=res_content, session_id=api_request.session_id, is_new_user=False)
                    else:
                        response = ChatMessageResponse(
                            session_id=api_request.session_id, reply=res_content, role="assistant",
                            metadata=ChatMessageMetadata(
                                tokens_used=0,
                                latency_ms=int((time.time() - ctx.start_time) * 1000),
                                perf_breakdown={"fast_path_type": fast_path_result.fast_path_type}
                            )
                        )
                    
                    if idempotency_key:
                        await self.idempotency.save(idempotency_key, response.model_dump())
                        
                    return response
                except Exception:
                    if not release_lock:
                        # Fallback manual release to prevent lock leakage if response generation/caching fails.
                        # We rely on LockPort.release being idempotent.
                        await self.lock.release(session_key, lock_token)
                    raise

            # ═══════════════════════════════════════════════════════════════
            # PHASE 1: ASYNC PARALLEL READS
            # ═══════════════════════════════════════════════════════════════

            with tracer.step("resolve_context"):
                # Sequential execution to prevent SQLAlchemy AsyncSession concurrency errors
                ctx.is_new_user = await self.profile.sync_profile(ctx.user_id, api_request.user_profile)
                session = await self.persistence.session_service.get_or_create_session(api_request.session_id, ctx.user_id)
                ctx.session_id = session.session_id
                log_meta["session_id"] = str(ctx.session_id)

            with tracer.step("load_memory"):
                payload = await self.memory.get_conversation_context(ctx.session_id, api_request.message)

            user_tokens = await self.tokens.count_tokens(api_request.message)

            # ═══════════════════════════════════════════════════════════════
            # PHASE 2: AI GENERATION (may fail — handled gracefully)
            # ═══════════════════════════════════════════════════════════════

            domain_res = None
            generation_failed = False

            try:
                with tracer.step("domain_execution"):
                    context = payload.get("context") or ChatContext()
                    context.session_id = str(ctx.session_id)
                    context.user_id = str(ctx.user_id)  # ← from token, never from body

                    domain_req = ChatDomainRequest(
                        message=api_request.message,
                        history=payload.get("history", []),
                        context=context,
                        role=api_request.role
                    )

                    domain_res = await asyncio.wait_for(
                        self.domain.generate_response(domain_req),
                        timeout=settings.AI_REQUEST_TIMEOUT
                    )

            except Exception as ai_exc:
                generation_failed = True
                logger.error(
                    "pipeline.ai_generation_failed",
                    extra={**log_meta, "error": str(ai_exc), "error_type": type(ai_exc).__name__}
                )

            # ═══════════════════════════════════════════════════════════════
            # PHASE 3: RESPONSE PERSISTENCE
            # ═══════════════════════════════════════════════════════════════

            if generation_failed or domain_res is None:
                # ── Fallback: Save error message as assistant response ──
                fallback_content = "حصلت مشكلة في توليد الرد، حاول مرة تانية"
                
                try:
                    await self._persist(
                        ctx.session_id, api_request.role, api_request.message, user_tokens,
                        "assistant", fallback_content, 0,
                        {"status": "failed_generation", "intent": "error"}, "error", session.current_summary
                    )
                except Exception as persist_exc:
                    logger.critical("double_failure_ai_and_persist", extra={**log_meta, "error": str(persist_exc)})
                return self._build_fallback_response(ctx, fallback_content)

            else:
                # ── Success: Build response immediately, persist in background ──
                response = self._build_api_response(ctx, domain_res, tracer=tracer)

                # Extract plain value BEFORE scheduling — ORM object will be
                # expired/detached by the time the background task runs.
                current_summary = session.current_summary

                # ═══ PERFORMANCE BREAKDOWN LOG (before background schedule) ═══
                tracer.log_summary(logger, request_id=request_id, user_id=str(ctx.user_id), session_id=str(ctx.session_id))
                logger.info("pipeline_success", extra={**log_meta, "latency_ms": int((time.time() - ctx.start_time)*1000), "perf_breakdown": tracer.as_dict()})

                if background_tasks:
                    # [NOTE: GRACEFUL SHUTDOWN ASSUMPTIONS]
                    # FastAPI BackgroundTasks are tied to the ASGI request lifecycle.
                    # During shutdown, Uvicorn will wait for these tasks to finish before 
                    # triggering the lifespan teardown (which closes Redis/ARQ pools).
                    # HOWEVER, this guarantee is limited by:
                    # 1. Uvicorn's `timeout_graceful_shutdown` (default varies, often small).
                    # 2. Kubernetes `terminationGracePeriodSeconds` (default 30s) before SIGKILL.
                    # Ensure both settings in production infra are comfortably larger than 
                    # the worst-case execution time of `_normal_path_background_finalize`
                    # (including DB write + Redis write + ARQ enqueue retries).
                    background_tasks.add_task(
                        self._normal_path_background_finalize,
                        ctx, api_request, domain_res, user_tokens,
                        current_summary, idempotency_key, response,
                        session_key, lock_token,
                    )
                    release_lock = False
                else:
                    # Inline fallback (e.g. testing without BackgroundTasks)
                    try:
                        metadata = {"intent": domain_res.intent, "route": domain_res.route}
                        await self._persist(
                            ctx.session_id, api_request.role, api_request.message, user_tokens,
                            domain_res.role, domain_res.content, domain_res.ai_tokens,
                            metadata, domain_res.intent, current_summary,
                        )
                        await self.memory.persist_interaction(
                            ctx.session_id, api_request.message, domain_res.content, domain_res.intent
                        )
                        if idempotency_key:
                            await self.idempotency.save(idempotency_key, response.model_dump())
                    except Exception as inline_persist_exc:
                        logger.error("inline_persistence_failed", extra={**log_meta, "error": str(inline_persist_exc)})

                return response

        except (HTTPException, AppException) as e:
            logger.warning("pipeline_domain_error", extra={**log_meta, "error": str(e)})
            raise
        except Exception as e:
            logger.error("pipeline_system_error", extra={**log_meta, "error": str(e), "error_type": type(e).__name__}, exc_info=True)
            raise HTTPException(status_code=500, detail="Service Failure")

        finally:
            if release_lock:
                await self.lock.release(session_key, lock_token)

    def _build_api_response(
        self, ctx: WorkflowContext, res: ChatDomainResponse, tracer: Optional[PerformanceTracer] = None
    ) -> Union[ChatIntegrationResponse, ChatMessageResponse]:
        content = res.content or "عذراً، لم أستطع العثور على رد مناسب حالياً. يرجى المحاولة مرة أخرى."
        if ctx.auth_mode == "INTEGRATION":
            return ChatIntegrationResponse(response=content, session_id=ctx.session_id, is_new_user=ctx.is_new_user)
        
        perf = tracer.as_dict() if tracer and settings.DEBUG else None
        if perf:
            perf["token_usage"] = res.token_breakdown
            
        return ChatMessageResponse(
            session_id=ctx.session_id, reply=content, role=res.role,
            metadata=ChatMessageMetadata(
                tokens_used=res.ai_tokens,
                latency_ms=int((time.time() - ctx.start_time) * 1000),
                perf_breakdown=perf
            )
        )

    def _build_fallback_response(self, ctx: WorkflowContext, fallback_content: str) -> Union[ChatIntegrationResponse, ChatMessageResponse]:
        """Build a graceful response when AI generation fails."""
        if ctx.auth_mode == "INTEGRATION":
            return ChatIntegrationResponse(response=fallback_content, session_id=ctx.session_id, is_new_user=ctx.is_new_user)
        return ChatMessageResponse(
            session_id=ctx.session_id, reply=fallback_content, role="assistant",
            metadata=ChatMessageMetadata(tokens_used=0, latency_ms=int((time.time() - ctx.start_time) * 1000))
        )

    async def _normal_path_background_finalize(
        self, ctx: WorkflowContext, api_request: ChatMessageRequest,
        domain_res: ChatDomainResponse, user_tokens: int,
        current_summary: str, idempotency_key: Optional[str],
        response: Union[ChatIntegrationResponse, ChatMessageResponse],
        session_key: str, lock_token: str,
    ):
        """
        Executes Normal Path Phase 3 persistence in the background.
        Takes ownership of the session lock to guarantee strict message ordering,
        releasing it only after all writes are complete.
        """
        try:
            # 1. SQL Persistence
            metadata = {"intent": domain_res.intent, "route": domain_res.route}
            await self._persist(
                ctx.session_id, api_request.role, api_request.message, user_tokens,
                domain_res.role, domain_res.content, domain_res.ai_tokens,
                metadata, domain_res.intent, current_summary,
            )
            # 2. Redis Memory Persist (+ summarization trigger via arq)
            await self.memory.persist_interaction(
                ctx.session_id, api_request.message, domain_res.content, domain_res.intent
            )
            # 3. Idempotency Cache (best-effort)
            if idempotency_key:
                await self.idempotency.save(idempotency_key, response.model_dump())
        except Exception as e:
            logger.error(
                "normal_path_persistence_failed",
                extra={"session_id": str(ctx.session_id), "error": str(e)},
                exc_info=True,
            )
        finally:
            await self.lock.release(session_key, lock_token)

    async def _fast_path_background_finalize(
        self, ctx: WorkflowContext, api_request: ChatMessageRequest, 
        ai_content: str, intent: str, session_key: str, lock_token: str
    ):
        """
        Executes Fast Path context resolution and persistence in the background.
        Takes ownership of the session lock to guarantee strict message ordering,
        releasing it only after persistence is complete.
        """
        try:
            await self._fast_path_finalize(ctx, api_request, ai_content, intent)
        finally:
            await self.lock.release(session_key, lock_token)

    async def _fast_path_finalize(
        self, ctx: WorkflowContext, api_request: ChatMessageRequest, 
        ai_content: str, intent: str
    ):
        """
        Runs context resolution and persistence for Fast Path hits.
        """
        try:
            # 1. Resolve Context (create session, sync profile) sequentially for DB safety
            ctx.is_new_user = await self.profile.sync_profile(ctx.user_id, api_request.user_profile)
            session = await self.persistence.session_service.get_or_create_session(api_request.session_id, ctx.user_id)
            ctx.session_id = session.session_id
            
            user_tokens = await self.tokens.count_tokens(api_request.message)
            
            # 2. Persist in SQL
            await self._persist(
                ctx.session_id, api_request.role, api_request.message, user_tokens,
                "assistant", ai_content, 0,
                {"intent": intent, "route": "fast_path"}, intent, session.current_summary
            )
            
            # 3. Persist in Redis
            await self.memory.persist_interaction(
                ctx.session_id, api_request.message, ai_content, intent
            )
            logger.info("fast_path_finalized", extra={"session_id": str(ctx.session_id)})
        except Exception as e:
            logger.error("fast_path_persistence_failed", extra={"error": str(e)}, exc_info=True)

    async def _persist(
        self, session_id, user_role, user_content, user_tokens,
        ai_role, ai_content, ai_tokens, metadata, intent, summary
    ):
        """
        Executes writes inline to guarantee message order consistency.
        Uses a fresh session wrapper internally.
        """
        async with ChatbotSessionLocal() as db_session:
            try:
                msg_repo = MessageRepository(db_session)
                session_repo = SessionRepository(db_session)
                
                # 1. Insert User Message
                await msg_repo.create({
                    "session_id": session_id, "role": user_role, 
                    "content": user_content, "token_count": user_tokens
                }, commit=False)
                
                # 2. Insert Assistant Message
                await msg_repo.create({
                    "session_id": session_id, "role": ai_role, 
                    "content": ai_content, "token_count": ai_tokens, "metadata": metadata
                }, commit=False)
                
                # 3. Update Session Intent
                session_obj = await session_repo.get(session_id)
                if session_obj:
                    await session_repo.update(session_obj, {
                        "current_intent": intent, "current_summary": summary
                    }, commit=False)
                
                await db_session.commit()
                logger.info("persistence_success", extra={"session_id": str(session_id)})
            except Exception as e:
                await db_session.rollback()
                logger.error("persistence_failed", extra={"session_id": str(session_id), "error": str(e)}, exc_info=True)
                raise
