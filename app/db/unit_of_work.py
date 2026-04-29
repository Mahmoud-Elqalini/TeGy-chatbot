from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class AsyncUnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._transaction = None

    async def __aenter__(self) -> "AsyncUnitOfWork":
        self._transaction = await self.session.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._transaction is None:
            return
        if exc_type is not None:
            await self._transaction.rollback()
        elif self._transaction.is_active:
            await self._transaction.commit()

    async def commit(self) -> None:
        if self._transaction is not None and self._transaction.is_active:
            await self._transaction.commit()

    async def rollback(self) -> None:
        if self._transaction is not None and self._transaction.is_active:
            await self._transaction.rollback()
