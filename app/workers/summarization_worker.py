from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_redis
from app.infrastructure.adapters.redis_lock_adapter import RedisLockAdapter
from app.infrastructure.adapters.redis_state_adapter import RedisStateAdapter
from app.core.container import ServiceContainer
from app.services.chat_memory_service import ChatMemoryService
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.message_service import MessageService
from app.repositories.message_repo import MessageRepository
from app.ai.summarizer import Summarizer


async def run_summarization_job(session_id: Union[str, uuid.UUID], message_count: int, chatbot_db: AsyncSession, response_generator) -> Optional[str]:
    """
    Background job to summarize a chat session and persist it.
    Hardened for:
    1. Source of Truth (Postgres History)
    2. Atomic Decrement (No race condition on new messages)
    3. Bucket Lock Re-verification
    """
    redis_client = await get_redis()
    lock_adapter = RedisLockAdapter(redis_client)
    state_adapter = RedisStateAdapter(redis_client)
    
    session_key = str(session_id)
    lock_key = f"lock:summary:{session_key}"
    bucket = message_count // 10
    bucket_key = f"processed_summary_bucket:{session_key}:{bucket}"
    
    # 1. Acquire Distributed Lock
    lock_token = await lock_adapter.acquire(lock_key, ttl=120)
    if not lock_token:
        logger.info("summarization_skipped_locked", extra={"session_id": session_key})
        return None

    try:
        # 2. Redis Bucket Lock Re-verification
        bucket_status = await state_adapter.get_state(bucket_key)
        if bucket_status == "processed":
            logger.info("summarization_skipped_redis_processed", extra={"session_id": session_key, "bucket": bucket})
            return None

        # 3. DB-Level Final Idempotency Guard (Point 3 Hardening)
        from app.repositories.summary_repo import SummaryRepository
        summary_repo = SummaryRepository(chatbot_db)
        latest_version = await summary_repo.get_latest_version(session_id)
        if latest_version >= bucket:
            logger.info("summarization_skipped_db_processed", extra={"session_id": session_key, "bucket": bucket, "latest_version": latest_version})
            # Sync redis state just in case it was lost
            await state_adapter.set_state(bucket_key, "processed", ttl=86400*7)
            return None

        # 4. Initialize services
        session_service = ServiceContainer._build_session_service(chatbot_db, redis_client)
        msg_service = MessageService(MessageRepository(chatbot_db))
        persistence = ChatPersistenceService(msg_service, session_service)
        memory_service = ChatMemoryService(state_adapter, msg_service) # Pass msg_service for reliable history
        summarizer = Summarizer(response_generator)
        
        # 4. Source of Truth: Fetch History from DB (PostgreSQL)
        # We fetch the last 30 messages to ensure high quality context
        db_messages = await msg_service.get_session_history(session_id, limit=30)
        history = [{"role": m.role, "content": m.content} for m in db_messages]
        
        if not history:
            logger.warning("summarization_aborted_no_history", extra={"session_id": session_key})
            return None
            
        # 5. Call LLM
        summary_data = await summarizer.summarize(messages=history)
        
        # 6. Persist to PostgreSQL & Update context cache
        await persistence.finalize_session(session_id, {"summary": summary_data}, version=bucket)
        await memory_service.save_summary(session_id, summary_data.get("session_summary"))
        
        # 7. Atomic State Update (DECRBY)
        # We subtract ONLY the count we enqueued, preserving messages that arrived in-between
        count_key = f"chat:session:{session_key}:count"
        await state_adapter.decrement(count_key, message_count)
        
        # Mark bucket as 'processed'
        await state_adapter.set_state(bucket_key, "processed", ttl=86400*7)
        
        logger.info("summarization_success", extra={"session_id": session_key, "bucket": bucket, "summarized_msgs": message_count})
        return summary_data.get("session_summary")
        
    finally:
        await lock_adapter.release(lock_key, lock_token)
