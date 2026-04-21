import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func, Uuid
from sqlalchemy.orm import relationship
from app.db.database import Base

class ModelSetting(Base):
    __tablename__ = "model_settings"

    model_setting_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    model_name = Column(String(100), nullable=False)
    system_prompt = Column(Text, nullable=True)

    # Relationships
    session_links = relationship("SessionModelSetting", back_populates="model_setting", cascade="all, delete-orphan")


class SessionModelSetting(Base):
    __tablename__ = "session_model_settings"

    session_id = Column(Uuid, ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True)
    model_setting_id = Column(Uuid, ForeignKey("model_settings.model_setting_id", ondelete="CASCADE"), primary_key=True)
    activated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    session = relationship("Session", back_populates="model_settings")
    model_setting = relationship("ModelSetting", back_populates="session_links")
