import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SessionCreate(BaseModel):
    channel: str | None = Field(default="web", max_length=50)
    model_setting_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=150)
    system_prompt: str | None = Field(default=None, max_length=2000)


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=150)
    status: str | None = Field(default=None, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def check_at_least_one_field(cls, data: dict) -> dict:
        if not data:
            raise ValueError("At least one field (title or status) must be provided for update.")
        return data


class SessionRead(BaseModel):
    session_id: uuid.UUID
    model_setting_id: uuid.UUID | None = None
    title: str | None = None
    channel: str | None = None
    status: str
    current_intent: str | None = None
    current_summary: str | None = None
    created_at: datetime
    last_active: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionListRead(BaseModel):
    """Lightweight schema for list view."""
    session_id: uuid.UUID
    model_setting_id: uuid.UUID | None = None
    title: str | None = None
    channel: str | None = None
    status: str
    created_at: datetime
    last_active: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedSessions(BaseModel):
    items: list[SessionListRead]
    total: int
    skip: int
    limit: int
