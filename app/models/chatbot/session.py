from __future__ import annotations

import uuid
import enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.chatbot.base import ChatbotBase

if TYPE_CHECKING:
    from app.models.chatbot.message import Message
    from app.models.chatbot.session_memory import SessionMemory
    from app.models.chatbot.session_summary import ConvSummary
    from app.models.chatbot.model_settings import ModelSettings


class SessionStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    idle = "idle"
    archived = "archived"


class Session(ChatbotBase):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model_setting_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_settings.model_setting_id", ondelete="SET NULL"))
    title: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(50), default="web", server_default="web")
    status: Mapped[SessionStatus] = mapped_column(SQLEnum(SessionStatus, native_enum=False), default=SessionStatus.active, server_default="active")
    current_intent: Mapped[str | None] = mapped_column(String(255))
    current_summary: Mapped[str | None] = mapped_column(Text)
    last_active: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    model_setting: Mapped["ModelSettings"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    memory_entries: Mapped[list["SessionMemory"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    conv_summaries: Mapped[list["ConvSummary"]] = relationship(back_populates="session", cascade="all, delete-orphan")
