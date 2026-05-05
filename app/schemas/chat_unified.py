import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.message_schema import ChatMessage, MessageRole


# --- Enums ---




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


class ChatMessageRequest(BaseModel):
    """
    Main Chat Request Model.

    - In USER mode (JWT auth): user_id is resolved from the token and ignored if sent.
    - In INTEGRATION mode (API Key auth): user_id is required in the body.
    """
    user_id: uuid.UUID | None = Field(None, description="Required for INTEGRATION mode. Ignored for USER mode (resolved from JWT).")
    session_id: uuid.UUID | None = Field(None, description="Existing session ID. If None, a new session is created.")
    message: str = Field(min_length=1, max_length=5000, description="The user message content. Max 5000 characters.")
    role: MessageRole = Field(MessageRole.user, description="Role of the message sender.")
    user_profile: UserProfile | None = Field(None, description="Required on first message in INTEGRATION mode for new sessions.")


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
    messages: list[ChatMessage]
    total: int
    skip: int
    limit: int

    model_config = ConfigDict(from_attributes=True)
