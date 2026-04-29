from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


from app.core.config import settings


chatbot_engine = create_async_engine(
    settings.CHATBOT_DATABASE_URL,
    echo=settings.DEBUG or settings.SQL_ECHO,
    pool_pre_ping=settings.SQL_POOL_PRE_PING,
    pool_recycle=settings.SQL_POOL_RECYCLE,
    pool_size=settings.SQL_POOL_SIZE,
    max_overflow=settings.SQL_MAX_OVERFLOW,
)

ChatbotSessionLocal = async_sessionmaker(
    bind=chatbot_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)




async def get_chatbot_db() -> AsyncGenerator[AsyncSession, None]:
    async with ChatbotSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
