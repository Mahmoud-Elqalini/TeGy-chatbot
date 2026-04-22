import uuid
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class MessageRoleEnum(str, Enum):
    user = 'user'
    assistant = 'assistant'
    system = 'system'

class MessageStatusEnum(str, Enum):
    pending = 'pending'
    completed = 'completed'
    failed = 'failed'

class MessageBase(BaseModel):
    content: str
    role: MessageRoleEnum = Field(description="Role of the message sender")
    status: MessageStatusEnum = Field(default=MessageStatusEnum.completed, description="The processing status of the message")

class MessageCreate(MessageBase):
    session_id: uuid.UUID

class MessageRead(MessageBase):
    message_id: uuid.UUID
    session_id: uuid.UUID
    sending_time: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ChatResponse(BaseModel):
    status: str
    should_summarize: bool
    session_id: uuid.UUID
    user_message: MessageRead
    assistant_message: MessageRead
