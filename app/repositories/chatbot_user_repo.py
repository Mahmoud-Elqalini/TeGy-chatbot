from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseException
from app.models.chatbot.user import ChatbotUser


class ChatbotUserRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(
        self,
        user_id: uuid.UUID | str,
        name: str,
        email: str,
        gender: str,
    ) -> tuple[ChatbotUser, bool]:
        try:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
            user = await self.db.get(ChatbotUser, user_uuid)

            # -------------------------
            # USER EXISTS → UPDATE ONLY IF CHANGED
            # -------------------------
            if user is not None:
                changed = False

                if user.name != name:
                    user.name = name
                    changed = True

                if user.email != email:
                    user.email = email
                    changed = True

                if user.gender != gender:
                    user.gender = gender
                    changed = True

                if changed:
                    user.updated_at = datetime.now(timezone.utc)
                    await self.db.flush()
                    await self.db.refresh(user)

                return user, False

            # -------------------------
            # USER NOT FOUND → INSERT
            # -------------------------
            now = datetime.now(timezone.utc)

            user = ChatbotUser(
                user_id=user_uuid,
                name=name,
                email=email,
                gender=gender,
                created_at=now,
                updated_at=now,
            )
            self.db.add(user)
            await self.db.flush()
            await self.db.refresh(user)
            return user, True

        except Exception as exc:
            await self.db.rollback()
            raise DatabaseException("Failed to upsert chatbot user") from exc
        