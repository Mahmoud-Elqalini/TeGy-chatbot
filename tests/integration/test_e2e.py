from fastapi.testclient import TestClient
from app.main import app
from app.api.v1.dependencies import get_current_user
from app.ai.providers.base import LLMResponse

class MockGeminiProvider:
    provider_name = "mock_gemini"
    turn = 0
    
    async def generate(self, request):
        self.turn += 1
        if self.turn == 1:
            return LLMResponse(
                content="",
                model="mock",
                provider="mock",
                tool_calls=[{"id": "call_1", "name": "get_events", "arguments": {}}]
            )
        else:
            return LLMResponse(
                content=f"Final Answer based on tools: {request.user_input}",
                model="mock",
                provider="mock"
            )

    async def count_tokens(self, content, model=None):
        return 10

async def mock_get_current_user():
    return "00000000-0000-0000-0000-000000000001"

app.dependency_overrides[get_current_user] = mock_get_current_user

def run_test():
    with TestClient(app) as client:
        # Override the providers in the app state manually
        app.state.gemini_provider = MockGeminiProvider()
        app.state.response_generator.provider = app.state.gemini_provider
        
        print("1. Creating Session...")
        response = client.post(
            "/api/v1/chat/session", 
            json={"channel": "web", "system_prompt": "You are a helpful assistant."},
            headers={"Authorization": "Bearer fake-token"}
        )
        print("Session Response:", response.status_code, response.text)
        if response.status_code != 200:
            return

        session_id = response.json().get("session_id")
        
        print(f"\n2. Sending Message to Session {session_id}...")
        response = client.post(
            "/api/v1/chat/message",
            json={
                "session_id": session_id,
                "content": "What events are available?"
            },
            headers={"Authorization": "Bearer fake-token"}
        )
        print("Message Response:", response.status_code, response.text)

if __name__ == "__main__":
    run_test()
