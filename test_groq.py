import asyncio
import os
from app.core.config import settings
from app.ai.providers.groq_provider import GroqProvider
from app.ai.providers.base import LLMRequest

async def test_groq():
    provider = GroqProvider()
    request = LLMRequest(
        model=settings.GROQ_MODEL,
        system_prompt="You are a helpful assistant.",
        history=[],
        user_input="اعرض كل الأحداث في مصر خلال السنة",
        tools=[{
            "name": "search_events",
            "description": "Search for events",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }],
        tool_choice="auto"
    )
    
    try:
        response = await provider._single_attempt(request)
        print("Success:", response)
    except Exception as e:
        print("Failed:", type(e))
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            print(e.response.text)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_groq())
