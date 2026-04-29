import asyncio

import pytest

from app.db.main_repositories import build_main_repository_bundle
from app.models.main_models import MainUser
from app.repositories.event_repo import EventRepository
from app.repositories.interaction_repo import InteractionRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.support_case_repo import SupportCaseRepository
from app.repositories.ticket_repo import TicketRepository
from app.repositories.ticket_type_repo import TicketTypeRepository
from app.repositories.user_repo import UserRepository
from app.schemas.sync import SyncBatchRequest
from app.services.sync_service import SyncDependencies, SyncService


@pytest.mark.asyncio
async def test_sync_upsert_idempotency(integration_dbs):
    main_db, chatbot_db = integration_dbs
    main_db.add(MainUser(id=1, email="student@test.com", username="student", is_verified=True, is_deleted=False))
    await main_db.commit()

    service = SyncService(
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

    first = await service.sync_batch(SyncBatchRequest())
    second = await service.sync_batch(SyncBatchRequest())

    assert first.users.created == 1
    assert second.users.skipped == 1
