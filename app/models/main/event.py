import enum
from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.main.base import MainBase

class MainEventStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    ended = "ended"
    cancelled = "cancelled"

class Event(MainBase):
    """
    Full SQLAlchemy model for Main DB events.
    """
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_source_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True) # Used for sync tracking if needed
    organizer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    category: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[dict | list | None] = mapped_column(JSONB)
    start_date: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_deadline: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    place: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(100))
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[MainEventStatus] = mapped_column(SQLEnum(MainEventStatus, name="event_status"), nullable=False)
    visibility: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
