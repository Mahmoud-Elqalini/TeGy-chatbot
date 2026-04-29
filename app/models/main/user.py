from __future__ import annotations

import enum
from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.main.base import MainBase


class MainGenderType(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class MainUser(MainBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[MainGenderType | None] = mapped_column(SQLEnum(MainGenderType, name="gender_type"))
    city: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
