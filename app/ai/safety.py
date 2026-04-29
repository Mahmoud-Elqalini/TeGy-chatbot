from __future__ import annotations

from app.core.exceptions import ValidationException


class InputSafetyGuard:
    def validate_user_message(self, content: str) -> None:
        if not content.strip():
            raise ValidationException("Message content cannot be blank.")
        if len(content) > 5000:
            raise ValidationException("Message content exceeds the allowed length.")

    def gemini_safety_settings(self) -> list[dict[str, str]]:
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]


class ResponseValidator:
    def validate_response(self, content: str) -> str:
        cleaned = content.strip()
        if not cleaned:
            raise ValidationException("AI response was empty.")
        return cleaned
