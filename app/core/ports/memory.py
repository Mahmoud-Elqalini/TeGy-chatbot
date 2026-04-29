import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MemoryPort(ABC):
    """
    Interface for conversation memory and state storage.
    Follows Hexagonal Architecture (Port).
    """

    @abstractmethod
    async def get_context(self, session_id: uuid.UUID, message: str) -> Dict[str, Any]:
        """Loads conversation history and metadata context."""
        pass

    @abstractmethod
    async def update_after_user(self, session_id: uuid.UUID, message: str) -> bool:
        """Updates state after user message. Returns True if summarization is needed."""
        pass

    @abstractmethod
    async def update_after_assistant(self, session_id: uuid.UUID, content: str, intent: str) -> None:
        """Updates state after assistant response."""
        pass

    @abstractmethod
    async def get_summary(self, session_id: uuid.UUID) -> str | None:
        """Retrieves session summary if available."""
        pass
