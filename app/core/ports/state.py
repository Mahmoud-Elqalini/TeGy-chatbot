from abc import ABC, abstractmethod
from typing import Any, Dict


class StatePort(ABC):
    """
    Low-level State Storage Port.
    Provides raw access to state blobs. No business logic.
    """

    @abstractmethod
    async def get_state(self, key: str) -> Dict[str, Any] | None:
        """Retrieves raw state by key."""
        pass

    @abstractmethod
    async def set_state(self, key: str, value: Dict[str, Any], ttl: int | None = None) -> None:
        """Persists raw state blob."""
        pass

    @abstractmethod
    async def delete_state(self, key: str) -> None:
        """Removes state."""
        pass
