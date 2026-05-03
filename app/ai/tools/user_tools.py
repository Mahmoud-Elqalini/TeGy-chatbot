"""
User-related tools for the AI chatbot.
"""
import uuid


def register(tool_registry):
    """Register all user-related tools."""

    @tool_registry.register(
        name="get_user_profile",
        description="Fetch the current user's profile and settings.",
        parameters={"type": "object", "properties": {}}
    )
    async def get_user_profile(user_id: str | uuid.UUID = "00000000-0000-0000-0000-000000000001", **kwargs):
        """Mock function to simulate getting user data."""
        return {"user_id": str(user_id), "name": "Mock User", "preferences": ["Technology", "AI"]}
