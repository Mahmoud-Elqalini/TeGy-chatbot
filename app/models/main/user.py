from __future__ import annotations
from typing import Union, Optional, Any, List, Dict

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
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    age: Mapped[Optional[int]] = mapped_column(Integer)
    gender: Mapped[Optional[MainGenderType]] = mapped_column(SQLEnum(MainGenderType, name="gender_type"))
    city: Mapped[Optional[str]] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))