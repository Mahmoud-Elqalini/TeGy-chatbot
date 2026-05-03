import json
import logging
from typing import Any, Dict, List, Optional
from app.ai.response_generator import ResponseGenerator

logger = logging.getLogger(__name__)

class Summarizer:
    """
    Production-grade conversation summarization engine.
    Follows strict JSON output rules and existing system constraints.
    """

    SUMMARIZATION_PROMPT = """
You are a production-grade conversation summarization engine inside an existing chatbot backend system.

⚠️ CRITICAL SYSTEM CONSTRAINT:
You are NOT allowed to redesign, extend, or modify the system architecture.
You MUST strictly follow the existing database design and output format.
Do NOT invent new tables, fields, or logic.

This system already has:
1. sessions.current_summary → stores the latest full summary (overwritten each update)
2. conv_summaries table → stores versioned historical summaries

You are ONLY responsible for generating structured data that fits this existing system.

────────────────────────────────────
INPUT:
You will receive:
- Latest chat messages in the session:
{messages}

- Optional previous summary:
{previous_summary}

────────────────────────────────────
YOUR TASK:
- Analyze full conversation context
- Update the existing memory intelligently
- Maintain consistency with previous summaries
- Extract user intent and important facts
- Improve memory quality over time

────────────────────────────────────
STRICT OUTPUT RULES:
- Output MUST be valid JSON ONLY
- NO explanations
- NO extra fields beyond the required schema
- DO NOT introduce any new structure outside this format

────────────────────────────────────
REQUIRED OUTPUT FORMAT:

{{
  "session_summary": "Updated full conversation summary to be stored in sessions.current_summary",
  
  "conv_summary": "Short compressed memory for quick retrieval",
  
  "key_points": [
    "Important user fact or preference",
    "Important context or behavior",
    "Important decision or intent"
  ],
  
  "intent": "Current dominant user intent",
  
  "version_note": "Short note describing what changed in this update"
}}

────────────────────────────────────
IMPORTANT BEHAVIOR RULES:
- NEVER change database design assumptions
- NEVER create new storage concepts
- NEVER output anything outside the given JSON format
- NEVER include raw conversation logs
- Always treat this as a memory update system, not a chatbot response system
- Be consistent across updates
- Improve memory quality, do not expand system scope

────────────────────────────────────
GOAL:
Produce a stable, production-safe memory update that fits directly into:
- sessions.current_summary
- conv_summaries (versioned storage)
"""

    def __init__(self, response_generator: ResponseGenerator):
        self.response_generator = response_generator

    async def summarize(self, messages: List[Dict[str, Any]], previous_summary: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates a structured summary from chat history.
        """
        formatted_messages = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        
        prompt = self.SUMMARIZATION_PROMPT.format(
            messages=formatted_messages,
            previous_summary=previous_summary or "No previous summary available."
        )

        try:
            response_text = await self.response_generator.generate_simple(prompt)
            # Find JSON block if LLM included extra text
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end != 0:
                response_text = response_text[start:end]
            
            return json.loads(response_text)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback to basic join if LLM fails
            return {
                "session_summary": "\n".join([m['content'] for m in messages[-5:]]),
                "conv_summary": "Auto-generated fallback summary.",
                "key_points": [],
                "intent": "unknown",
                "version_note": "Fallback due to error"
            }
