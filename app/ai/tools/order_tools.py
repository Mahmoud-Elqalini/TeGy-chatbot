"""
Order-related tools for the AI chatbot.
"""
import uuid


def register(tool_registry):
    """Register all order-related tools."""

    @tool_registry.register(
        name="search_orders",
        description="Find all past orders made by the user.",
        parameters={"type": "object", "properties": {}}
    )
    async def search_orders(user_id: str | uuid.UUID = "00000000-0000-0000-0000-000000000001", **kwargs):
        """Mock function to simulate order search."""
        return [{"order_id": 101, "event_id": 1, "status": "confirmed", "amount": 150.0}]
