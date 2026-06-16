"""
Event-related tools for the AI chatbot.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.semantic_search_service import SemanticSearchService
from app.repositories.main.event_repo import MainEventRepository
from app.ai.tool_registry import ToolRegistry


@ToolRegistry.register_tool(
    name="search_events",
    description="search_events(q, limit) -> returns events list",
    parameters={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Search query such as 'cairo music events this weekend'"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return (max 5)",
                "maximum": 5,
                "default": 5
            }
        },
        "required": ["q"]
    },
    metadata={"category": "events"}
)
async def search_events(q: str, limit: int = 5, main_db: AsyncSession = None, **kwargs):
    """
    Pure orchestrator tool:
    1. Calls the semantic search API (Async HTTP).
    2. Calls the repository to fetch live data (Async DB).
    3. Merges and returns the data.
    """
    if not q or not q.strip():
        return {"error": "Missing search query"}

    if main_db is None:
        return {"error": "Internal Error: main_db session not injected."}

    # Step 1: External API Call
    api_data = await SemanticSearchService.search(q, limit)
    
    raw_hits = api_data.get("hits", [])
    
    source_ids = [
        int(x)
        for x in raw_hits
        if isinstance(x, int) or str(x).isdigit()
    ]

    # Step 2: Database Call
    event_repo = MainEventRepository(main_db)
    raw_events = await event_repo.get_events_by_ids(source_ids)

    # Step 3: Prune and return merged response
    events = []
    for ev in raw_events:
        events.append({
            "id": ev.get("source_id"),
            "name": ev.get("name"),
            "start_date": ev.get("start_date"),
            "end_date": ev.get("end_date"),
            "location": f"{ev.get('place', '')}, {ev.get('city', '')}".strip(" ,"),
            "price": ev.get("price"),
            "status": ev.get("status"),
            "short_description": (ev.get("description") or "")[:200]
        })

    return {
        "events": events
    }
