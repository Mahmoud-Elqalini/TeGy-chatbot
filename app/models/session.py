import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func, Uuid
from sqlalchemy.orm import relationship
from app.db.database import Base

class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    current_intent = Column(String(100), nullable=True)
    current_summary = Column(Text, nullable=True)
    last_active = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    summaries = relationship("ConvSummary", back_populates="session", cascade="all, delete-orphan")
    model_settings = relationship("SessionModelSetting", back_populates="session", cascade="all, delete-orphan")
