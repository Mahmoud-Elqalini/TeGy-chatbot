import uuid
from sqlalchemy import Column, Text, DateTime, ForeignKey, func, Uuid, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.db.database import Base

class Message(Base):
    __tablename__ = "messages"

    message_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid, ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    role = Column(SQLEnum('user', 'assistant', 'system', name='message_roles'), nullable=False)
    sending_time = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    session = relationship("Session", back_populates="messages")
