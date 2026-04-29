import pytest

from app.ai.memory_manager import MemoryManager
from app.services.memory_service import MemoryService
from app.services.message_service import MessageService
from app.services.session_service import SessionService
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.models.main_models import MainUser
from app.repositories.event_repo import EventRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.interaction_repo import InteractionRepository
from app.repositories.ticket_repo import TicketRepository
from app.repositories.ticket_type_repo import TicketTypeRepository
from app.repositories.support_case_repo import SupportCaseRepository
from app.services.sync_service import SyncDependencies, SyncService
from app.db.main_repositories import build_main_repository_bundle
from app.schemas.sync import SyncBatchRequest
from app.schemas.session import SessionCreate
from app.models.chatbot.message import MessageRole


class RedisAdapter:
    def __init__(self, client):
        self.client = client

    async def get(self, key):
        return await self.client.get(key)

    async def set(self, key, value, ttl):
        await self.client.set(key, value, ex=ttl)

    async def set_nx(self, key, value, ttl):
        return await self.client.set(key, value, nx=True, ex=ttl)

    async def delete(self, key):
        await self.client.delete(key)

    async def lpush(self, key, value):
        await self.client.lpush(key, value)

    async def ltrim(self, key, start, end):
        await self.client.ltrim(key, start, end)

    async def lrange(self, key, start, end):
        return await self.client.lrange(key, start, end)

    async def expire(self, key, ttl):
        await self.client.expire(key, ttl)

    async def exists(self, key):
        return (await self.client.exists(key)) > 0

    async def incr(self, key):
        return await self.client.incr(key)

    async def hset(self, key, field=None, value=None, mapping=None):
        if mapping:
            await self.client.hset(key, mapping=mapping)
        else:
            await self.client.hset(key, field, value)

    async def hgetall(self, key):
        return await self.client.hgetall(key)

    def pipeline(self):
        return self.client.pipeline()


@pytest.mark.asyncio
async def test_session_creation_and_message_persistence(integration_dbs, integration_redis):
    main_db, chatbot_db = integration_dbs
    main_db.add(MainUser(id=2, email="chat@test.com", username="chat-user", is_verified=True, is_deleted=False))
    await main_db.commit()

    sync_service = SyncService(
        main_db=main_db,
        chatbot_db=chatbot_db,
        repos=SyncDependencies(
            users=UserRepository(chatbot_db),
            events=EventRepository(chatbot_db),
            ticket_types=TicketTypeRepository(chatbot_db),
            orders=OrderRepository(chatbot_db),
            tickets=TicketRepository(chatbot_db),
            interactions=InteractionRepository(chatbot_db),
            support_cases=SupportCaseRepository(chatbot_db),
        ),
        main_repos=build_main_repository_bundle(main_db),
    )
    await sync_service.sync_batch(SyncBatchRequest())

    memory_service = MemoryService(MemoryManager(RedisAdapter(integration_redis)))
    session_service = SessionService(SessionRepository(chatbot_db), UserRepository(chatbot_db), memory_service)
    message_service = MessageService(MessageRepository(chatbot_db))

    session = await session_service.create_session(SessionCreate(channel="web"), 2)
    message = await message_service.save_message(session.id, MessageRole.user, "hello integration")

    assert session.user_id == 2
    assert message.content == "hello integration"
