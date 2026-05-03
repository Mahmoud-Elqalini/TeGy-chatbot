"""
Event-related tools for the AI chatbot.
"""


def register(tool_registry):
    """Register all event-related tools."""

    @tool_registry.register(
        name="get_events",
        description="Get a list of available events from the database.",
        parameters={"type": "object", "properties": {}}
    )
    async def get_events(**kwargs):
        """Mock function to simulate fetching events."""
        return [
            {"id": 1, "name": "Tech Conference 2026", "date": "2026-05-15", "location": "Cairo"},
            {"id": 2, "name": "AI Summit", "date": "2026-06-20", "location": "Dubai"}
        ]
