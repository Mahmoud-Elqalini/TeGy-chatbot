import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class SessionBase(BaseModel):
    title: Optional[str] = None

class SessionCreate(SessionBase):
    pass

class SessionUpdate(BaseModel):
    title: Optional[str] = None
    current_intent: Optional[str] = None

class SessionRead(SessionBase):
    session_id: uuid.UUID
    user_id: uuid.UUID
    current_intent: Optional[str] = None
    last_active: datetime
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
