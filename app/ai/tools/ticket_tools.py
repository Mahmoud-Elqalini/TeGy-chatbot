"""
Ticket-related tools for the AI chatbot.
"""


def register(tool_registry):
    """Register all ticket-related tools."""

    @tool_registry.register(
        name="create_ticket",
        description="Book a ticket for a specific event.",
        parameters={
            "type": "object",
            "properties": {
                "event_id": {"type": "integer", "description": "The unique ID of the event to book."}
            },
            "required": ["event_id"]
        }
    )
    async def create_ticket(event_id: int, **kwargs):
        """Mock function to simulate ticket creation."""
        return {"status": "success", "ticket_id": f"TKT-{event_id}-999", "event_id": event_id}
