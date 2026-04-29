from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


from app.core.config import settings


main_engine = create_async_engine(
    settings.MAIN_DATABASE_URL,
    echo=settings.DEBUG or settings.SQL_ECHO,
    pool_pre_ping=settings.SQL_POOL_PRE_PING,
    pool_recycle=settings.SQL_POOL_RECYCLE,
    pool_size=settings.SQL_POOL_SIZE,
    max_overflow=settings.SQL_MAX_OVERFLOW,
)

MainSessionLocal = async_sessionmaker(
    bind=main_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)




async def get_main_db() -> AsyncGenerator[AsyncSession, None]:
    async with MainSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
