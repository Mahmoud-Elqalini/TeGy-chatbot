import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(min_length=8, description="Password must be at least 8 characters long")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class UserRead(UserBase):
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
