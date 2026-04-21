import uuid
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class MessageRoleEnum(str, Enum):
    user = 'user'
    assistant = 'assistant'
    system = 'system'

class MessageBase(BaseModel):
    content: str
    role: MessageRoleEnum = Field(description="Role of the message sender")

class MessageCreate(MessageBase):
    session_id: uuid.UUID

class MessageRead(MessageBase):
    message_id: uuid.UUID
    session_id: uuid.UUID
    sending_time: datetime
    
    model_config = ConfigDict(from_attributes=True)
