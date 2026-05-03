from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.chatbot.base import ChatbotBase


if TYPE_CHECKING:
    from app.models.chatbot.session import Session


class ConvSummary(ChatbotBase):
    __tablename__ = "conv_summaries"
    __table_args__ = (
        UniqueConstraint("session_id", "version", name="uq_summary_version"),
    )

    summarize_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="conv_summaries")
