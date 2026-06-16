from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.message_schema import ChatMessage, MessageRole


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
    perf_breakdown: Optional[Dict[str, Any]] = Field(None, description="Performance timing breakdown per pipeline step (debug only).")


# --- Request Models ---



class ChatIntegrationRequest(BaseModel):
    """
    Integration Request Model (Shared secret auth).
    """
    user_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    message: str
    role: str = "user"
    user_profile: Optional[UserProfile] = None

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

    - USER mode (JWT): user_id is IGNORED — identity comes exclusively from the JWT token.
    - INTEGRATION mode (API Key): user_id is REQUIRED in the body to identify the end-user.
    """
    user_id: Optional[uuid.UUID] = Field(None, description="Only used in INTEGRATION mode. Ignored in USER mode (resolved from JWT).")
    session_id: Optional[uuid.UUID] = Field(None, description="Existing session ID. If None, a new session is created.")
    message: str = Field(min_length=1, max_length=5000, description="The user message content. Max 5000 characters.")
    role: MessageRole = Field(MessageRole.user, description="Role of the message sender.")
    user_profile: Optional[UserProfile] = Field(None, description="Required on first message in INTEGRATION mode for new sessions.")


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