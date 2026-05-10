from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chatbot_user_repo import ChatbotUserRepository
from app.schemas.chat_unified import UserProfile


class UserProfileService:
    """
    Handles user profile synchronization and persistence.
    Separates infrastructure/DB concerns from core business logic.
    """

    def __init__(self, db: AsyncSession):
        self.repo = ChatbotUserRepository(db)

    async def sync_profile(self, user_id: uuid.UUID, profile: Optional[UserProfile]) -> bool:
        """
        Synchronizes user profile data if provided.
        Returns True if a new user was created.
        """
        if not profile:
            return False
        _, is_new = await self.repo.upsert(
            user_id=user_id,
            name=profile.name,
            email=profile.email,
            gender=profile.gender
        )
        return is_new