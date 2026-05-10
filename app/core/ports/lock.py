from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
from abc import ABC, abstractmethod


class LockPort(ABC):
    """
    Safe Distributed Lock Interface.
    Uses tokens to ensure atomic and secure release.
    """

    @abstractmethod
    async def acquire(self, key: str, ttl: int = 30) -> Optional[str]:
        """
        Acquires a lock. 
        Returns a unique token if successful, None otherwise.
        """
        pass

    @abstractmethod
    async def release(self, key: str, token: str) -> bool:
        """
        Releases a lock only if the token matches.
        Returns True if released, False otherwise.
        """
        pass