import asyncio
from datetime import datetime, timezone

import pytest

from app.ai.intent_detector import IntentDetector
from app.ai.prompt_builder import PromptBuilder
from app.ai.providers.base import LLMResponse
from app.ai.safety import InputSafetyGuard, ResponseValidator
from app.schemas.chat import ChatMessageRequest
from app.services.chat_service import ChatService


class FakeSessionService:
    async def get_session_model_for_user(self, session_id: int, user_id: int):
        return type(
            "Session",
            (),
            {
                "id": session_id,
                "user_id": user_id,
                "user_source_id": "u-1",
                "channel": "web",
                "current_intent": None,
                "current_summary": None,
            },
        )()

    async def touch_session(self, session_id: int, current_intent=None, current_summary=None):
        return None


class FakeMessageService:
    def __init__(self):
        self.counter = 0

    async def save_message(self, session_id: int, role, content: str, metadata=None, token_count=None):
        self.counter += 1
        return type(
            "Message",
            (),
            {
                "id": self.counter,
                "session_id": session_id,
                "role": role,
                "content": content,
                "token_count": 1,
                "metadata": metadata,
                "created_at": datetime.now(timezone.utc),
            },
        )()


class FakeMemoryService:
    async def initialize_session_context(self, session, system_prompt=None):
        return None

    async def after_user_message(self, session_id: int, content: str) -> bool:
        return False

    async def build_llm_payload(self, session_id: int, user_message: str):
        return {"context": type("Ctx", (), {"system_prompt": "", "current_summary": "", "current_intent": "", "channel": "web"})(), "model": "test", "history": [], "user_input": user_message}

    async def after_assistant_message(self, session_id: int, content: str, detected_intent=None):
        return None


class FakeSupportService:
    async def create_case_from_chat(self, user_id: int, subject: str, description: str):
        return None


class FakeResponseGenerator:
    async def generate(self, request):
        return LLMResponse(content="ok", model="test", provider="fake")


def test_chat_service_returns_success_response():
    service = ChatService(
        session_service=FakeSessionService(),
        message_service=FakeMessageService(),
        memory_service=FakeMemoryService(),
        support_service=FakeSupportService(),
        intent_detector=IntentDetector(),
        prompt_builder=PromptBuilder(),
        response_generator=FakeResponseGenerator(),
        safety_guard=InputSafetyGuard(),
        response_validator=ResponseValidator(),
    )

    response = asyncio.run(service.send_message(1, ChatMessageRequest(session_id=1, content="hello")))
    assert response.status == "success"
    assert response.assistant_message.content == "ok"
