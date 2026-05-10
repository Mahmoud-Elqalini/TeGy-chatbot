from __future__ import annotations
from typing import Union, Optional, Any, List, Dict

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.models.chatbot.user import ChatbotUser
from app.repositories.base_repo import BaseRepository


class ChatbotUserRepository(BaseRepository[ChatbotUser]):

    def __init__(self, db: AsyncSession):
        super().__init__(model=ChatbotUser, db=db, id_field="user_id")

    async def upsert(
        self,
        user_id: Union[uuid.UUID, str],
        name: str,
        email: str,
        gender: str,
    ) -> tuple[ChatbotUser, bool]:
        try:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
            now = datetime.now(timezone.utc)

            # Use PostgreSQL-specific ON CONFLICT for atomic upsert
            from sqlalchemy.dialects.postgresql import insert
            
            stmt = insert(ChatbotUser).values(
                user_id=user_uuid,
                name=name,
                email=email,
                gender=gender,
                created_at=now,
                updated_at=now
            ).on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "name": name,
                    "email": email,
                    "gender": gender,
                    "updated_at": now
                }
            ).returning(ChatbotUser)

            result = await self.db.execute(stmt)
            user = result.scalar_one()
            
            # Note: returns True if created_at == updated_at (approximate for 'is_new')
            return user, (user.created_at == user.updated_at)

        except Exception as exc:
            await self.db.rollback()
            from app.core.observability import get_logger
            get_logger(__name__).error(f"Upsert failed: {exc}")
            raise DatabaseException(f"Failed to upsert chatbot user: {exc}") from exc