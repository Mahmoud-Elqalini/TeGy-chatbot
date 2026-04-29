from abc import ABC, abstractmethod


class TokenPort(ABC):
    """
    Interface for token counting and metrics.
    Ensures domain doesn't depend on AI provider internals.
    """

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Counts the number of tokens in a given string."""
        pass
