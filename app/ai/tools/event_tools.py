"""
Event-related tools for the AI chatbot.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.semantic_search_service import SemanticSearchService
from app.repositories.main.event_repo import MainEventRepository
from app.ai.tool_registry import ToolRegistry


@ToolRegistry.register_tool(
    name="search_events",
    description=(
        "Semantic search for live events. "
        "Use this when the user wants to find events, browse events, "
        "or get recommendations for events. "
        "This tool searches semantically, then fetches the latest event data from the original MSSQL database."
    ),
    parameters={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Search query such as 'cairo music events this weekend'"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return"
            }
        },
        "required": ["q"]
    },
    metadata={"category": "events"}
)
async def search_events(q: str, limit: int = 8, main_db: AsyncSession = None, **kwargs):
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
            "source_id": ev.get("source_id"),
            "name": ev.get("name"),
            "category": ev.get("category"),
            "price": ev.get("price"),
            "start_date": ev.get("start_date"),
            "place": ev.get("place"),
            "city": ev.get("city"),
            "description_summary": (ev.get("description")[:150] + "...") if ev.get("description") else None,
            "is_online": ev.get("is_online"),
            "ticket_count": ev.get("ticket_count"),
            "status": ev.get("status"),
        })

    return {
        "query": q,
        "returned_ids": source_ids,
        "events_found": len(events),
        "events": events,
    }
