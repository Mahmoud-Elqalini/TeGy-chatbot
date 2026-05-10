from __future__ import annotations
from typing import Union, Optional, Any, List, Dict

import logging
import re

from app.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

ALLOWED_HISTORY_ROLES = {"user", "assistant"}

INJECTION_PATTERNS = [
    r"ignore\s+(Union[previous, all])\s+instructions?",
    r"you\s+are\s+now",
    r"new\s+system\s+prompt",
    r"disregard\s+",
    r"forget\s+everything",
    r"switch\s+to",
    r"become\s+a",
    r"from\s+now\s+on",
    r"pretend\s+(you\s+Union[are, to]\s+be)",
    r"your\s+real\s+instructions\s+are",
    r"act\s+as\s+",
    r"\[SYSTEM\s*:",
    r"\[ADMIN\s*:",
    r"\[INSTRUCTION\s*:",
]


class InputSafetyGuard:
    def validate_user_message(self, content: str) -> None:
        if not content.strip():
            raise ValidationException("Message content cannot be blank.")
        if len(content) > 5000:
            raise ValidationException("Message content exceeds the allowed length.")

        lower_content = content.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, lower_content):
                logger.warning(f"security.identity_override_attempt_detected: pattern={pattern}")
                raise ValidationException("I cannot process this request. My system identity is fixed.")

    def gemini_safety_settings(self) -> List[Dict[str, str]]:
        """
        Relaxes safety thresholds to prevent StopCandidateException during 
        innocent conversations. We rely on our own InputSafetyGuard for primary checks.
        """
        return [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]


class ResponseValidator:
    def validate_response(self, content: str) -> str:
        cleaned = content.strip()
        if not cleaned:
            raise ValidationException("AI response was empty.")
        return cleaned

    def sanitize_tool_output(self, tool_output: str) -> str:
        if not tool_output:
            return tool_output
        lower = tool_output.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, lower):
                logger.warning("tool.output.injection_detected", extra={"pattern": pattern})
                return "[REDACTED: Suspicious content detected in tool output]"
        return tool_output

    def sanitize_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not history:
            return []

        clean = []
        for msg in history[-5:]:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")
            if role not in ALLOWED_HISTORY_ROLES:
                logger.warning(f"history.sanitize: rejected invalid role '{role}'")
                continue

            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            content = content[:2000]

            lower_content = content.lower()
            for pattern in INJECTION_PATTERNS:
                if re.search(pattern, lower_content):
                    logger.warning(f"history.sanitize: dropped message with injection pattern: {pattern}")
                    break
            else:
                clean.append({"role": role, "content": content})

        return clean