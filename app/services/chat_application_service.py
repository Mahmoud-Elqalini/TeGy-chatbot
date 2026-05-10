from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
import logging
import time
import asyncio
from fastapi import HTTPException, status, BackgroundTasks
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
from app.services.chat_service import ChatService
from app.services.idempotency_service import IdempotencyService
from app.services.user_profile_service import UserProfileService
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.chat_memory_service import ChatMemoryService
from app.ai.summarizer import Summarizer

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

    async def execute(
        self,
        auth: AuthContext,
        api_request: ChatMessageRequest,
        idempotency_key: Optional[str] = None
    ) -> Union[ChatIntegrationResponse, ChatMessageResponse]:
        """
        Resilient Distributed Pipeline.

        Guarantees:
          1. User message is ALWAYS persisted (even if AI fails).
          2. Assistant response is saved only on successful generation.
          3. On AI failure, a fallback assistant message is saved with status='failed_generation'.
          4. Session creation + user message persist even if the AI response fails.

        Token-based identity: user_id is ALWAYS resolved from AuthContext.
        """
        request_id = str(uuid.uuid4())

        # ── Identity Resolution (Single Source of Truth: Token) ──
        ctx = WorkflowContext(
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            auth_mode=auth.mode,
            start_time=time.time()
        )

        # Idempotency Check
        if idempotency_key:
            cached_response = await self.idempotency.get(idempotency_key)
            if cached_response:
                logger.info("idempotency_hit", extra={"request_id": request_id, "idempotency_key": idempotency_key})
                if auth.mode == "INTEGRATION":
                    return ChatIntegrationResponse.model_validate(cached_response)
                return ChatMessageResponse.model_validate(cached_response)

        log_meta = {"request_id": request_id, "user_id": str(ctx.user_id), "session_id": str(api_request.session_id)}
        logger.info("pipeline_start", extra=log_meta)

        # Circuit Breaker Check
        if await self.resilience.is_circuit_open("ai_service"):
            if not await self.resilience.allow_probe("ai_service"):
                logger.error("circuit_breaker_open", extra=log_meta)
                raise HTTPException(status_code=503, detail="Service unavailable")

        # Acquire Lock
        session_key = str(api_request.session_id or ctx.user_id)
        lock_token = await self.lock.acquire(session_key, ttl=60)
        if not lock_token:
            logger.warning("concurrency_lock_failed", extra=log_meta)
            raise HTTPException(status_code=429, detail="Concurrent request in progress.")

        try:
            # ═══════════════════════════════════════════════════════════════
            # PHASE 1: GUARANTEED PERSISTENCE (always runs)
            # Session creation + user message are committed regardless of AI outcome.
            # ═══════════════════════════════════════════════════════════════

            # Step 1: Resolve Context (session creation happens here)
            step_start = time.time()
            ctx.is_new_user = await self.profile.sync_profile(ctx.user_id, api_request.user_profile)
            session = await self.persistence.session_service.get_or_create_session(api_request.session_id, ctx.user_id)
            ctx.session_id = session.session_id
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "resolve_context", "duration_ms": int((time.time() - step_start)*1000)})

            # Step 2: Load Memory
            step_start = time.time()
            payload = await self.memory.get_conversation_context(ctx.session_id, api_request.message)
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "load_memory", "duration_ms": int((time.time() - step_start)*1000)})

            # Step 3: Save User Message (ALWAYS — even if AI fails later)
            step_start = time.time()
            user_tokens = await self.tokens.count_tokens(api_request.message)
            await asyncio.wait_for(
                self.persistence.save_message(ctx.session_id, api_request.role, api_request.message, user_tokens),
                timeout=settings.DB_OPERATION_TIMEOUT
            )
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "save_input", "duration_ms": int((time.time() - step_start)*1000)})

            # ═══════════════════════════════════════════════════════════════
            # PHASE 2: AI GENERATION (may fail — handled gracefully)
            # ═══════════════════════════════════════════════════════════════

            domain_res = None
            generation_failed = False

            try:
                step_start = time.time()
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
                logger.info("pipeline.step_completed", extra={**log_meta, "step": "domain_execution", "duration_ms": int((time.time() - step_start)*1000)})

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
                    await asyncio.wait_for(
                        self.persistence.save_message(
                            ctx.session_id, "assistant", fallback_content, 0,
                            metadata={"status": "failed_generation", "intent": "error"}
                        ),
                        timeout=settings.DB_OPERATION_TIMEOUT
                    )
                    await self.persistence.finalize_session(ctx.session_id, {"intent": "error", "summary": session.current_summary})
                    logger.info("pipeline.fallback_saved", extra=log_meta)
                except Exception as persist_exc:
                    logger.error("pipeline.fallback_persist_failed", extra={**log_meta, "error": str(persist_exc)})
                    # Continue anyway — user seeing a response is more important than DB persistence

                return self._build_fallback_response(ctx, fallback_content)

            else:
                # ── Success: Save assistant response ──
                step_start = time.time()
                await asyncio.wait_for(
                    self.persistence.save_message(
                        ctx.session_id, domain_res.role, domain_res.content, domain_res.ai_tokens,
                        metadata={"intent": domain_res.intent, "route": domain_res.route}
                    ),
                    timeout=settings.DB_OPERATION_TIMEOUT
                )
                logger.info("pipeline.step_completed", extra={**log_meta, "step": "save_output", "duration_ms": int((time.time() - step_start)*1000)})

                # Memory Persist & Background Summarization
                step_start = time.time()
                should_summarize, updated_history = await self.memory.persist_interaction(
                    ctx.session_id, api_request.message, domain_res.content, domain_res.intent
                )

                await self.persistence.finalize_session(ctx.session_id, {"intent": domain_res.intent, "summary": session.current_summary})
                logger.info("pipeline.step_completed", extra={**log_meta, "step": "finalize", "duration_ms": int((time.time() - step_start)*1000)})

                # Response construction
                response = self._build_api_response(ctx, domain_res)
                if idempotency_key:
                    await self.idempotency.save(idempotency_key, response.model_dump())

                logger.info("pipeline_success", extra={**log_meta, "latency_ms": int((time.time() - ctx.start_time)*1000)})
                return response

        except (HTTPException, AppException) as e:
            logger.warning("pipeline_domain_error", extra={**log_meta, "error": str(e)})
            raise
        except Exception as e:
            logger.error("pipeline_system_error", extra={**log_meta, "error": str(e), "error_type": type(e).__name__}, exc_info=True)
            raise HTTPException(status_code=500, detail="Service Failure")

        finally:
            await self.lock.release(session_key, lock_token)

    def _build_api_response(self, ctx: WorkflowContext, res: ChatDomainResponse) -> Union[ChatIntegrationResponse, ChatMessageResponse]:
        content = res.content or "عذراً، لم أستطع العثور على رد مناسب حالياً. يرجى المحاولة مرة أخرى."
        if ctx.auth_mode == "INTEGRATION":
            return ChatIntegrationResponse(response=content, session_id=ctx.session_id, is_new_user=ctx.is_new_user)
        return ChatMessageResponse(
            session_id=ctx.session_id, reply=content, role=res.role,
            metadata=ChatMessageMetadata(tokens_used=res.ai_tokens, latency_ms=int((time.time() - ctx.start_time) * 1000))
        )

    def _build_fallback_response(self, ctx: WorkflowContext, fallback_content: str) -> Union[ChatIntegrationResponse, ChatMessageResponse]:
        """Build a graceful response when AI generation fails."""
        if ctx.auth_mode == "INTEGRATION":
            return ChatIntegrationResponse(response=fallback_content, session_id=ctx.session_id, is_new_user=ctx.is_new_user)
        return ChatMessageResponse(
            session_id=ctx.session_id, reply=fallback_content, role="assistant",
            metadata=ChatMessageMetadata(tokens_used=0, latency_ms=int((time.time() - ctx.start_time) * 1000))
        )
