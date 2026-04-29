import uuid
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Enums ---

class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    agent = "agent"  # Unified/V2 role
    system = "system"
    tool = "tool"


# --- Common Components ---

class UserProfile(BaseModel):
    """
    Basic user profile information used for personalization.
    """
    name: str
    email: str
    gender: str


class ChatMessageMetadata(BaseModel):
    tokens_used: int = 0
    latency_ms: int = 0


# --- Request Models ---

class ChatMessageRequest(BaseModel):
    """
    Legacy V1 Request Model.
    """
    message: str = Field(min_length=1)
    session_id: uuid.UUID | None = None
    role: str = "user"


class ChatIntegrationRequest(BaseModel):
    """
    Integration Request Model (Shared secret auth).
    """
    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    message: str
    role: str = "user"
    user_profile: UserProfile | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_first_message(cls, data: dict) -> dict:
        session_id = data.get("session_id")
        user_profile = data.get("user_profile")
        if session_id is None and user_profile is None:
            raise ValueError("user_profile is required for new sessions (first message).")
        return data


class ChatMessageRequestV2(BaseModel):
    """
    Unified V2 Request Model.
    """
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1)
    role: MessageRole = MessageRole.user
    user_profile: UserProfile | None = None


# --- Response Models ---

class ChatMessageResponse(BaseModel):
    """
    Standard Response Model.
    """
    session_id: uuid.UUID
    reply: str
    role: str = "assistant"
    metadata: ChatMessageMetadata

    model_config = ConfigDict(from_attributes=True)


class ChatIntegrationResponse(BaseModel):
    """
    Integration-specific Response Model.
    """
    response: str
    session_id: uuid.UUID
    is_new_user: bool


class ChatHistoryResponse(BaseModel):
    """
    Session History Model.
    """
    session_id: uuid.UUID
    messages: list[dict]

    model_config = ConfigDict(from_attributes=True)
