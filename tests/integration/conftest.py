from collections.abc import AsyncIterator

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.db.chatbot_database import ChatbotBase
from app.db.main_database import MainBase
from app.models.chatbot import Event, Message, Order, Session, SupportCase, Ticket, TicketType, User, UserInteraction
from app.models.chatbot.failed_job import FailedJob


@pytest_asyncio.fixture(scope="session")
async def postgres_containers() -> AsyncIterator[tuple[str, str]]:
    main_pg = PostgresContainer("postgres:16")
    chatbot_pg = PostgresContainer("postgres:16")
    main_pg.start()
    chatbot_pg.start()
    try:
        main_url = main_pg.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
        chatbot_url = chatbot_pg.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
        yield main_url, chatbot_url
    finally:
        main_pg.stop()
        chatbot_pg.stop()


@pytest_asyncio.fixture(scope="session")
async def redis_container_url() -> AsyncIterator[str]:
    container = RedisContainer("redis:7")
    container.start()
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest_asyncio.fixture
async def integration_dbs(postgres_containers) -> AsyncIterator[tuple[AsyncSession, AsyncSession]]:
    main_url, chatbot_url = postgres_containers
    main_engine = create_async_engine(main_url)
    chatbot_engine = create_async_engine(chatbot_url)
    async with main_engine.begin() as conn:
        await conn.run_sync(MainBase.metadata.create_all)
    async with chatbot_engine.begin() as conn:
        await conn.run_sync(ChatbotBase.metadata.create_all)

    main_session_factory = async_sessionmaker(main_engine, expire_on_commit=False, class_=AsyncSession)
    chatbot_session_factory = async_sessionmaker(chatbot_engine, expire_on_commit=False, class_=AsyncSession)

    async with main_session_factory() as main_session, chatbot_session_factory() as chatbot_session:
        yield main_session, chatbot_session

    await main_engine.dispose()
    await chatbot_engine.dispose()


@pytest_asyncio.fixture
async def integration_redis(redis_container_url) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_container_url, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()
