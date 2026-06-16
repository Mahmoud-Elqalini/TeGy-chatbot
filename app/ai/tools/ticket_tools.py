"""
Ticket-related tools for the AI chatbot.
"""
from app.ai.tool_registry import ToolRegistry


@ToolRegistry.register_tool(
    name="create_ticket",
    description="create_ticket(event_id) -> returns booking confirmation",
    parameters={
        "type": "object",
        "properties": {
            "event_id": {"type": "integer", "description": "The unique ID of the event to book."}
        },
        "required": ["event_id"]
    },
    metadata={"category": "tickets"}
)
async def create_ticket(event_id: int, **kwargs):
    """Mock function to simulate ticket creation."""
    return {"status": "success", "ticket_id": f"TKT-{event_id}-999", "event_id": event_id}
