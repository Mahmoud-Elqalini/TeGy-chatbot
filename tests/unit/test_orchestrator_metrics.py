import asyncio
import os
from dotenv import load_dotenv

# Load env to ensure GEMINI_API_KEY is available
load_dotenv()

from app.ai.providers.factory import ProviderFactory
from app.ai.response_generator import ResponseGenerator
from app.ai.tool_registry import ToolRegistry
from app.ai.tools import discover_and_register
from app.services.ai_orchestrator import AIOrchestrator
from app.ai.prompt_loader import PromptLoader
from app.ai.prompt_builder import PromptBuilder
from app.schemas.chat_dtos import ChatContext

class DummyValidator:
    def validate_response(self, text): return text
    def sanitize_history(self, history): return history
    def sanitize_tool_output(self, text): return text

async def main():
    print("Loading prompts and tools...")
    PromptLoader.load_all()
    discover_and_register()
    
    print("Initializing LLM provider...")
    provider = ProviderFactory.initialize_provider_chain()
    generator = ResponseGenerator(provider)
    registry = ToolRegistry()
    
    orchestrator = AIOrchestrator(generator, DummyValidator(), registry)
    builder = PromptBuilder()
    
    context = ChatContext(session_id="test", user_id="test", channel="web", model_name="gemini")
    
    system_prompt = builder.build_system_prompt(context, "support_event")
    renderer_prompt = builder.build_renderer_prompt(context)
    
    payload = {
        "model": "gemini-2.5-flash",
        "system_prompt": system_prompt,
        "renderer_prompt": renderer_prompt,
        "history": [],
        "context": context
    }
    
    print("Sending query to Orchestrator: 'اعرض كل الأحداث في مصر خلال السنة'")
    content, tokens, tools, breakdown = await orchestrator.generate_complex(
        user_input="اعرض كل الأحداث في مصر خلال السنة",
        intent="support_event",
        payload=payload,
        session_id="test-session-123"
    )
    
    print("\n" + "="*50)
    print("🗣️  AI RESPONSE:")
    print("="*50)
    print(content)
    
    print("\n" + "="*50)
    print("📊  TOKEN METRICS (THE TRUTH):")
    print("="*50)
    for key, val in breakdown.items():
        print(f" - {key}: {val}")
    print(f" - TOTAL TOKENS: {tokens}")

if __name__ == "__main__":
    asyncio.run(main())
