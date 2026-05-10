from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
"""
Order-related tools for the AI chatbot.
"""
import uuid
from app.ai.tool_registry import ToolRegistry


@ToolRegistry.register_tool(
    name="search_orders",
    description="Find all past orders made by the user.",
    parameters={"type": "object", "properties": {}},
    metadata={"category": "orders"}
)
async def search_orders(user_id: Union[str, uuid.UUID] = None, **kwargs):
    """Mock function to simulate order search."""
    if user_id is None:
        return {"error": "Internal Error: user_id not injected."}
        
    return [{"order_id": 101, "event_id": 1, "status": "confirmed", "amount": 150.0}]