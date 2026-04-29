from app.core.ports.tokens import TokenPort
from typing import Callable, Awaitable


class LLMTokenAdapter(TokenPort):
    """
    Agnostic Infrastructure Adapter for token counting.
    Doesn't depend on AI Orchestrator internals, only a counter function.
    """

    def __init__(self, counter: Callable[[str], Awaitable[int]]):
        self._counter = counter

    async def count_tokens(self, text: str) -> int:
        return await self._counter(text)
