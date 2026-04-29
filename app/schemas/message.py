import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.chatbot.message import MessageRole


class MessageCreate(BaseModel):
    session_id: uuid.UUID
    role: MessageRole
    content: str
    token_count: int = 0
    metadata: dict[str, Any] | None = None


class MessageRead(BaseModel):
    message_id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    token_count: int
    metadata: dict[str, Any] | None = None
    sending_time: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_metadata_field(cls, value):
        if hasattr(value, "metadata_"):
            return {
                "message_id": value.message_id,
                "session_id": value.session_id,
                "role": value.role,
                "content": value.content,
                "token_count": value.token_count,
                "metadata": value.metadata_,
                "sending_time": value.sending_time,
            }
        return value
