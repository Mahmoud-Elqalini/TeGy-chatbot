from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Union, Any, Dict


class StatePort(ABC):
    """
    Low-level State Storage Port.
    Provides raw access to state blobs. No business logic.
    """

    @abstractmethod
    async def get_state(self, key: str) -> Optional[Any]:
        """Retrieves raw state by key."""
        pass

    @abstractmethod
    async def set_state(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Persists raw state blob."""
        pass

    @abstractmethod
    async def delete_state(self, key: str) -> None:
        """Removes state."""
        pass

    @abstractmethod
    async def increment(self, key: str, ttl: Optional[int] = None) -> int:
        """Atomsically increments a counter and returns the new value."""
        pass

    @abstractmethod
    async def decrement(self, key: str, amount: int) -> int:
        """Atomically decrements a counter by amount."""
        pass

    @abstractmethod
    async def set_nx(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Atomically sets a key if it does not exist (SETNX). Returns True if set."""
        pass
