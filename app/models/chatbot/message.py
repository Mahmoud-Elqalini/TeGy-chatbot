from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any

import uuid
from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.chatbot.base import ChatbotBase

if TYPE_CHECKING:
    from app.models.chatbot.session import Session


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    agent = "agent"
    system = "system"
    tool = "tool"


class Message(ChatbotBase):
    __tablename__ = "messages"

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(SQLEnum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    sending_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="messages")
