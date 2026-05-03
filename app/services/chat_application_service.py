import uuid
import logging
import time
import asyncio
from fastapi import HTTPException, status

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
        idempotency_key: str | None = None
    ) -> ChatIntegrationResponse | ChatMessageResponse:
        """
        Discrete 6-Step Distributed Pipeline.
        """
        request_id = str(uuid.uuid4())
        ctx = WorkflowContext(
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            auth_mode=auth.mode,
            start_time=time.time()
        )

        # 🟡 Structured Logging
        log_meta = {"request_id": request_id, "user_id": str(ctx.user_id), "session_id": str(api_request.session_id)}
        logger.info("pipeline_start", extra=log_meta)

        # 0. Distributed Circuit Breaker Check 🔴
        if await self.resilience.is_circuit_open("ai_service"):
            if not await self.resilience.allow_probe("ai_service"):
                logger.error("circuit_breaker_open", extra=log_meta)
                raise HTTPException(status_code=503, detail="Service unavailable")

        # 1. Acquire Atomic Safe Lock 🔴
        session_key = str(api_request.session_id or ctx.user_id)
        lock_token = await self.lock.acquire(session_key, ttl=60)
        if not lock_token:
            logger.warning("concurrency_lock_failed", extra=log_meta)
            raise HTTPException(status_code=429, detail="Concurrent request in progress.")

        try:
            # Step 1: Resolve Context
            step_start = time.time()
            ctx.is_new_user = await self.profile.sync_profile(ctx.user_id, api_request.user_profile)
            session = await self.persistence.session_service.get_or_create_session(api_request.session_id, ctx.user_id)
            ctx.session_id = session.session_id
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "resolve_context", "duration_ms": int((time.time() - step_start)*1000)})

            # Step 2: Load Memory
            step_start = time.time()
            payload = await self.memory.get_conversation_context(ctx.session_id, api_request.message)
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "load_memory", "duration_ms": int((time.time() - step_start)*1000)})

            # Step 3: Save Input
            step_start = time.time()
            user_tokens = await self.tokens.count_tokens(api_request.message)
            await asyncio.wait_for(
                self.persistence.save_message(ctx.session_id, api_request.role, api_request.message, user_tokens),
                timeout=settings.DB_OPERATION_TIMEOUT
            )
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "save_input", "duration_ms": int((time.time() - step_start)*1000)})
            
            # Step 4: Run Domain Execution with Distributed Resilience 🔴
            step_start = time.time()
            context = payload.get("context") or ChatContext()
            context.session_id = str(ctx.session_id)
            context.user_id = str(ctx.user_id)

            domain_req = ChatDomainRequest(
                message=api_request.message,
                history=payload.get("history", []),
                context=context,
                role=api_request.role
            )
            
            domain_res = await self._execute_domain_with_backoff(domain_req, log_meta)
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "domain_execution", "duration_ms": int((time.time() - step_start)*1000)})

            # Step 5: Save Output
            step_start = time.time()
            await asyncio.wait_for(
                self.persistence.save_message(
                    ctx.session_id, domain_res.role, domain_res.content, domain_res.ai_tokens,
                    metadata={"intent": domain_res.intent, "route": domain_res.route}
                ),
                timeout=settings.DB_OPERATION_TIMEOUT
            )
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "save_output", "duration_ms": int((time.time() - step_start)*1000)})

            # Step 6: Finalize
            step_start = time.time()
            should_summarize, updated_history = await self.memory.persist_interaction(
                ctx.session_id, api_request.message, domain_res.content, domain_res.intent
            )
            
            summary_data = None
            if should_summarize:
                # Use the new advanced summarizer with the ALREADY UPDATED history
                summary_data = await self.summarizer.summarize(
                    messages=updated_history,
                    previous_summary=session.current_summary
                )
                await self.memory.save_summary(ctx.session_id, summary_data.get("session_summary"))

            await self.persistence.finalize_session(ctx.session_id, {"intent": domain_res.intent, "summary": summary_data})
            logger.info("pipeline.step_completed", extra={**log_meta, "step": "finalize", "duration_ms": int((time.time() - step_start)*1000)})

            # Response construction
            response = self._build_api_response(ctx, domain_res)
            if ctx.idempotency_key:
                await self.idempotency.save(ctx.idempotency_key, response.model_dump())

            logger.info("pipeline_success", extra={**log_meta, "latency_ms": int((time.time() - ctx.start_time)*1000)})
            return response

        except Exception as e:
            logger.error("pipeline_error", extra={**log_meta, "error": str(e), "error_type": type(e).__name__}, exc_info=True)
            raise HTTPException(status_code=500, detail="Service Failure")
        
        finally:
            # 🔴 Truly Atomic Release (Lua)
            await self.lock.release(session_key, lock_token)

    async def _execute_domain_with_backoff(self, req: ChatDomainRequest, meta: dict) -> ChatDomainResponse:
        """Exponential Backoff + Distributed Failure Tracking 🔴."""
        for attempt in range(3):
            try:
                # 🟠 Timeout: 10 seconds
                res = await asyncio.wait_for(self.domain.generate_response(req), timeout=settings.AI_REQUEST_TIMEOUT)
                
                # 🟠 Reset failure count on success 🟠
                await self.resilience.record_success("ai_service")
                return res
                
            except (asyncio.TimeoutError, Exception) as e:
                # 🔴 Record Distributed Failure
                is_open = await self.resilience.record_failure("ai_service")
                if is_open:
                    logger.critical("circuit_breaker_triggered", extra=meta)
                
                if attempt == 2:
                    logger.error("ai_exhausted_retries", extra=meta)
                    raise
                
                wait_time = 0.5 * (2 ** attempt)
                logger.warning(f"ai_retry_attempt_{attempt+1}", extra={**meta, "wait_time": wait_time})
                await asyncio.sleep(wait_time)
        
        raise Exception("Execution unreachable")

    def _build_api_response(self, ctx: WorkflowContext, res: ChatDomainResponse) -> ChatIntegrationResponse | ChatMessageResponse:
        if ctx.auth_mode == "INTEGRATION":
            return ChatIntegrationResponse(response=res.content, session_id=ctx.session_id, is_new_user=ctx.is_new_user)
        return ChatMessageResponse(
            session_id=ctx.session_id, reply=res.content, role=res.role,
            metadata=ChatMessageMetadata(tokens_used=res.ai_tokens, latency_ms=int((time.time() - ctx.start_time) * 1000))
        )
