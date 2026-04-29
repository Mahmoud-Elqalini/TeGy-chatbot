import uuid
from dataclasses import dataclass
from typing import Any, Dict, List
from app.models.chatbot.message import MessageRole


@dataclass(frozen=True)
class ChatDomainRequest:
    """Pure domain data for AI processing."""
    message: str
    history: List[Dict[str, Any]]
    context: Dict[str, Any]
    role: str = "user"


@dataclass(frozen=True)
class ChatDomainResponse:
    """Pure domain result from AI generation."""
    content: str
    role: MessageRole
    intent: str
    confidence: float
    route: str
    ai_tokens: int
    tool_results: List[Dict[str, Any]] | None
    latency_ms: int


@dataclass
class WorkflowContext:
    """State carrier for the application workflow."""
    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    auth_mode: str = "USER"
    is_new_user: bool = False
    start_time: float = 0.0
