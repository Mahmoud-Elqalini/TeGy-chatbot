import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    channel: str | None = Field(default="web", max_length=50)
    model_setting_id: uuid.UUID | None = None
    title: str | None = None
    system_prompt: str | None = None


class SessionUpdate(BaseModel):
    channel: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=20)
    model_setting_id: uuid.UUID | None = None
    title: str | None = None
    current_intent: str | None = None
    current_summary: str | None = None


class SessionRead(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    model_setting_id: uuid.UUID | None = None
    title: str | None = None
    channel: str | None = None
    status: str
    current_intent: str | None = None
    current_summary: str | None = None
    created_at: datetime
    last_active: datetime

    model_config = ConfigDict(from_attributes=True)
