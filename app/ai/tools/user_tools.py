from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
"""
User-related tools for the AI chatbot.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.tool_registry import ToolRegistry
from app.repositories.chatbot_user_repo import ChatbotUserRepository


@ToolRegistry.register_tool(
    name="get_user_profile",
    description="Fetch the current user's profile and settings from the database.",
    parameters={"type": "object", "properties": {}},
    metadata={"roles": ["user", "admin"]}
)
async def get_user_profile(user_id: Union[str, uuid.UUID] = None, db: AsyncSession = None, **kwargs):
    """Fetch user profile from chatbot_users table."""
    if db is None or user_id is None:
        return {"error": "Internal Error: Database session or User ID not injected."}
    
    try:
        repo = ChatbotUserRepository(db)
        user = await repo.get(user_id)
        
        if not user:
            return {"error": f"User with ID {user_id} not found."}
            
        return {
            "user_id": str(user.user_id),
            "name": user.name,
            "email": user.email,
            "gender": user.gender,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    except Exception as e:
        return {"error": f"Failed to fetch user profile: {str(e)}"}