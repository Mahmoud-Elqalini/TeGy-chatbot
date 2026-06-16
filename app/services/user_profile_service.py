from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chatbot_user_repo import ChatbotUserRepository
from app.schemas.chat_unified import UserProfile
from app.core.ports.state import StatePort


class UserProfileService:
    """
    Handles user profile synchronization and persistence.
    Separates infrastructure/DB concerns from core business logic.
    """

    def __init__(self, db: AsyncSession, state_port: Optional[StatePort] = None):
        self.repo = ChatbotUserRepository(db)
        self.state = state_port

    async def sync_profile(self, user_id: uuid.UUID, profile: Optional[UserProfile]) -> bool:
        """
        Synchronizes user profile data if provided.
        Returns True if a new user was created.
        """
        if not profile:
            return False
            
        # OPTIMIZATION 2: Redis Throttling
        cache_key = None
        if self.state:
            # Create a deterministic hash of the profile data
            payload = f"{profile.name}|{profile.email}|{profile.gender}"
            profile_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
            cache_key = f"profile:sync:{user_id}:{profile_hash}"
            
            # Skip DB if this exact profile was synced recently
            recently_synced = await self.state.get_state(cache_key)
            if recently_synced:
                return False

        # Hit the DB only if data changed or 5-min TTL expired
        _, is_new = await self.repo.upsert(
            user_id=user_id,
            name=profile.name,
            email=profile.email,
            gender=profile.gender
        )
        
        # Save to cache on success
        if self.state and cache_key:
            await self.state.set_state(cache_key, True, ttl=300)
            
        return is_new