import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.message_repo import MessageRepository
from app.ai.tool_registry import ToolRegistry

MAX_HISTORY_TOKENS = 500_000


def estimate_text_tokens(text: str) -> int:
    """Rough conservative estimate (chars // 3)."""
    if not text:
        return 0
    return max(1, len(text) // 3)


def format_message(m) -> str:
    role = getattr(m, "role", "unknown")
    content = getattr(m, "content", "") or ""
    created_at = getattr(m, "sending_time", None)

    created_at_text = created_at.isoformat() if created_at else "unknown"
    return f"[{created_at_text}] {role}: {content}"


def trim_history_fifo(messages: List[Any], max_tokens: int) -> List[Any]:
    """Drops oldest messages first until history fits budget."""
    trimmed = list(messages)
    while trimmed:
        formatted = "\n\n".join(format_message(m) for m in trimmed)
        estimated_tokens = estimate_text_tokens(formatted)
        if estimated_tokens <= max_tokens:
            return trimmed
        trimmed.pop(0)
    return []


@ToolRegistry.register_tool(
    name="get_conversation_history",
    description="get_conversation_history(reason, max_tokens) -> returns previous messages if user refers to past context",
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Short reason why conversation history is needed (e.g., 'user asked about a previous event mentioned')."
            },
            "max_tokens": {
                "type": "integer",
                "description": "Optional token budget for the history snippet."
            }
        },
        "required": ["reason"]
    },
    metadata={"category": "system", "enabled": False}
)
async def get_conversation_history(
    reason: str,
    max_tokens: int = 500000,
    db: AsyncSession = None,
    session_id: uuid.UUID = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Fetch previous messages from the current conversation when needed.
    """
    if db is None or session_id is None:
        return {"error": "Internal Error: Database session or Session ID not injected."}

    token_budget = max(1_000, min(max_tokens, MAX_HISTORY_TOKENS))

    repo = MessageRepository(db)
    # Fetch a large chunk of history (e.g., last 1000 messages)
    rows = await repo.get_session_messages(session_id, limit=1000)

    # Filter to real conversation roles
    messages = [
        row for row in rows
        if row.role in {"user", "assistant"}
    ]

    trimmed_messages = trim_history_fifo(messages, token_budget)
    formatted_history = "\n\n".join(format_message(row) for row in trimmed_messages)

    return {
        "session_id": str(session_id),
        "reason": reason,
        "token_budget": token_budget,
        "total_messages_found": len(messages),
        "returned_messages": len(trimmed_messages),
        "history": formatted_history,
    }
