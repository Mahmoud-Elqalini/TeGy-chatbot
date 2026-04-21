import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ConvSummaryBase(BaseModel):
    summary: str
    version: int = 1

class ConvSummaryCreate(ConvSummaryBase):
    session_id: uuid.UUID

class ConvSummaryRead(ConvSummaryBase):
    summarize_id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
