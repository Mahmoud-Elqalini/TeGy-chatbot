import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from enum import Enum

class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    agent = "agent"
    system = "system"
    tool = "tool"


class ChatMessage(BaseModel):
    """
    Strongly-typed model for a single chat message.
    Used in session history responses instead of raw dicts.
    """
    message_id: uuid.UUID
    role: MessageRole
    content: str
    token_count: int = 0
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_")
    sending_time: datetime

    model_config = ConfigDict(from_attributes=True)
