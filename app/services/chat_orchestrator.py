import uuid
import logging
from typing import Dict, Any
from app.services.message_service import MessageService
from app.services.memory_service import MemoryService
from app.services.llm_service import LLMService
from app.core.exceptions import LLMUnavailableException, AppException
from app.schemas.message import MessageRoleEnum, MessageStatusEnum, ChatResponse, MessageRead
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ChatOrchestrator:
    def __init__(self, message_service: MessageService, memory_service: MemoryService, llm_service: LLMService):
        self.message_service = message_service
        self.memory_service = memory_service
        self.llm_service = llm_service

    async def handle_user_message(
        self, 
        session_id: uuid.UUID, 
        content: str
    ) -> ChatResponse:
        """
        The CORE BRAIN flow for executing a chat cycle:
        User -> DB -> Redis -> LLM -> DB -> Redis
        Returns an extensive dictionary. Routes handle bridging this to FastAPI models.
        """
        session_id_str = str(session_id)
        should_summarize = False
        summarize_lock_acquired = False

        try:
            # 1. Save user message to Database (Always completed natively)
            user_msg = await self.message_service.save_message(
                session_id=session_id, 
                role=MessageRoleEnum.user, 
                content=content, 
                status=MessageStatusEnum.completed
            )
            
            # 2. Update Redis Memory
            # should_summarize indicates if the route should spawn a background dictation process.
            # However, if True, the MemoryService will have natively acquired the lock.
            should_summarize = await self.memory_service.after_user_message(session_id_str, content)
            if should_summarize:
                summarize_lock_acquired = True
            
            # 3. Prepare Payload
            payload = await self.memory_service.build_llm_payload(session_id_str, content)
            if not payload:
                # Early return if memory crashes
                if summarize_lock_acquired:
                    await self.memory_service.release_summarize_lock(session_id_str)
                    
                return self._fallback_package(session_id_str, user_msg, "Internal memory error occurred.")

            # 4. Save Assistant Message as "pending"
            pending_ai_msg = await self.message_service.save_message(
                session_id=session_id, 
                role=MessageRoleEnum.assistant, 
                content="...", 
                status=MessageStatusEnum.pending
            )

            # 5. Call LLM
            try:
                ai_response_content = await self.llm_service.get_response(payload)
                
                # 6. Success Flow: Update AI message with response and "completed" status
                ai_msg = await self.message_service.finalize_message(
                    message_id=pending_ai_msg.message_id, 
                    status=MessageStatusEnum.completed, 
                    content=ai_response_content
                )
                
                # Update Redis Memory with AI response
                await self.memory_service.after_assistant_message(session_id_str, ai_response_content)
                
            except LLMUnavailableException as e:
                logger.error(f"LLM exhausted or failed severely for session {session_id_str}: {e}")
                # 6. Failure Flow: Update AI message as "failed" with fallback text
                fallback_content = "I'm having trouble connecting to my brain right now. Please try again later."
                
                # Protect DB interaction in fallback: we want UX to know about degradation even if DB fails
                try:
                    ai_msg = await self.message_service.finalize_message(
                        message_id=pending_ai_msg.message_id, 
                        status=MessageStatusEnum.failed, 
                        content=fallback_content
                    )
                except AppException as db_err:
                    logger.exception(f"Failed to save fallback AI message to DB natively: {db_err}")
                    # Create a mock ai_msg object just to return to the route
                    ai_msg = MessageRead(
                        message_id=uuid.uuid4(),
                        session_id=session_id,
                        sending_time=datetime.now(timezone.utc),
                        role=MessageRoleEnum.assistant,
                        status=MessageStatusEnum.failed,
                        content=fallback_content
                    )
                    
                return self._fallback_package(session_id_str, user_msg, ai_msg, should_summarize)

            return ChatResponse(
                status="success",
                should_summarize=should_summarize,
                session_id=session_id,
                user_message=user_msg,
                assistant_message=ai_msg
            )
        
        except Exception as e:
            logger.exception(f"Critical failure in Chat Orchestrator for session {session_id_str}")
            # If the session got locked before a deep crash disrupted the fallback, safely release it to prevent a perpetual lock leak.
            try:
                if summarize_lock_acquired:
                    await self.memory_service.release_summarize_lock(session_id_str)
            except Exception as release_err:
                logger.error(f"Failed to release summarize lock during critical orchestration crash: {release_err}")
                
            raise

    def _fallback_package(self, session_id: str, user_msg, ai_msg, should_summarize: bool = False) -> ChatResponse:
        """Provides a statically consistent footprint for Fallback routines"""
        # If ai_msg fails to be passed properly, build a strict dummy MessageRead
        if not hasattr(ai_msg, "model_dump"):
             ai_msg = MessageRead(
                 message_id=uuid.uuid4(),
                 session_id=uuid.UUID(session_id),
                 sending_time=datetime.now(timezone.utc),
                 content=str(ai_msg),
                 role=MessageRoleEnum.assistant,
                 status=MessageStatusEnum.failed
             )
             
        return ChatResponse(
            status="degraded",
            should_summarize=should_summarize,
            session_id=session_id,
            user_message=user_msg,
            assistant_message=ai_msg
        )
