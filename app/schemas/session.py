from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SessionCreate(BaseModel):
    channel: Optional[str] = Field(default="web", max_length=50)
    model_setting_id: Optional[uuid.UUID] = Field(default=uuid.UUID("88cc1f16-4a7e-46d6-8152-4790121e9a5d"))
    title: Optional[str] = Field(default=None, max_length=150)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=150)
    status: Optional[str] = Field(default=None, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def check_at_least_one_field(cls, data: dict) -> dict:
        if not data:
            raise ValueError("At least one field (title or status) must be provided for update.")
        return data


class SessionRead(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionListRead(BaseModel):
    """Lightweight schema for list view."""
    session_id: uuid.UUID
    model_setting_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    channel: Optional[str] = None
    status: str
    created_at: datetime
    last_active: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedSessions(BaseModel):
    items: list[SessionListRead]
    total: int
    skip: int
    limit: int