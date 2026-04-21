import uuid
from sqlalchemy import Column, Text, Integer, DateTime, ForeignKey, func, Uuid
from sqlalchemy.orm import relationship
from app.db.database import Base

class ConvSummary(Base):
    __tablename__ = "conv_summaries"

    summarize_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid, ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    session = relationship("Session", back_populates="summaries")
