from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.schemas.chat_unified import UserProfile


# ---------------------------------------------------------------------
# Atomic UPSERT Query
# ---------------------------------------------------------------------
# الهدف:
# - إدخال مستخدم جديد أو تحديث بياناته في نفس العملية
# - منع عمليات write غير ضرورية (no-op updates)
#
# Logic:
# - ON CONFLICT → handles duplicate user_id
# - IS DISTINCT FROM → prevents update if data didn't change
# - RETURNING (xmax = 0) → tells if row was newly inserted
# ---------------------------------------------------------------------
_UPSERT_SQL = """
INSERT INTO chatbot_users (
    user_id,
    name,
    email,
    gender,
    created_at,
    updated_at
)
VALUES (
    :user_id,
    :name,
    :email,
    :gender,
    now(),
    now()
)
ON CONFLICT (user_id) DO UPDATE
SET
    name       = EXCLUDED.name,
    email      = EXCLUDED.email,
    gender     = EXCLUDED.gender,
    updated_at = now()

-- Prevent unnecessary updates if data is identical
WHERE (chatbot_users.name,
       chatbot_users.email,
       chatbot_users.gender)
    IS DISTINCT FROM
      (EXCLUDED.name,
       EXCLUDED.email,
       EXCLUDED.gender)

-- Detect whether this was an INSERT (true) or UPDATE (false)
RETURNING (xmax = 0) AS is_new_user;
"""


# ---------------------------------------------------------------------
# Repository Layer
# ---------------------------------------------------------------------
class ChatbotUserRepository:
    """
    Handles persistence of chatbot user profiles.

    Responsibility:
    - Upsert user data efficiently
    - Avoid unnecessary writes
    - Return whether user is newly created
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------
    # Upsert user
    # -------------------------------------------------------------
    async def upsert(
        self,
        user_id: uuid.UUID,
        profile: UserProfile,
    ) -> bool:
        """
        Insert or update a chatbot user in a single atomic operation.

        Returns:
            True  → user was newly created
            False → user already existed (updated or unchanged)
        """

        result = await self.db.execute(
            text(_UPSERT_SQL),
            {
                "user_id": str(user_id),
                "name": profile.name,
                "email": profile.email,
                "gender": profile.gender,
            },
        )

        row = result.fetchone()

        # If no row returned → means no actual change happened
        # (because WHERE IS DISTINCT FROM blocked update)
        if row is None:
            return False

        return bool(row.is_new_user)