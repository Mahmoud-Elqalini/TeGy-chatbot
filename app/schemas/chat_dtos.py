from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import Union, Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.chatbot.message import MessageRole
from app.core.config import settings


class ChatContext(BaseModel):
    """
    Metadata and current state of a chat session.
    """
    system_prompt: str = ""
    current_intent: str = ""
    current_summary: str = ""
    channel: str = "web"
    model_name: str = Field(default=settings.GEMINI_MODEL)
    user_id: Optional[str] = None
    session_id: Optional[str] = None


@dataclass(frozen=True)
class ChatDomainRequest:
    """Pure domain data for AI processing."""
    message: str
    history: List[Dict[str, Any]]
    context: ChatContext
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
    session_id: Optional[uuid.UUID] = None
    idempotency_key: Optional[str] = None
    auth_mode: str = "USER"
    is_new_user: bool = False
    start_time: float = 0.0
