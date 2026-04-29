from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.chatbot_database import get_chatbot_db
from app.db.main_database import get_main_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_chatbot_db():
        yield session


async def get_chatbot_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_chatbot_db():
        yield session


async def get_main_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_main_db():
        yield session
