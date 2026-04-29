import asyncio

import pytest

from app.schemas.sync import SyncBatchRequest, SyncEntityResult, SyncUserPayload
from app.services.sync_service import SyncDependencies, SyncService


class FakeRepo:
    def __init__(self):
        self.items = {}
        self.seq = 1

    async def get_by_source_id(self, source_id):
        return self.items.get(source_id)

    async def create(self, values, commit=False):
        obj = type("Obj", (), {"id": self.seq, **values})()
        self.seq += 1
        key = values.get("user_source_id") or values.get("event_source_id") or values.get("ticket_type_source_id") or values.get("order_source_id") or values.get("ticket_source_id") or values.get("ui_source_id")
        self.items[key] = obj
        return obj

    async def update(self, existing, values, commit=False):
        for key, value in values.items():
            setattr(existing, key, value)
        return existing

    async def get(self, id):
        return None


class FakeMainUserRepo:
    def __init__(self):
        self.items = [
            type(
                "MainUser",
                (),
                {
                    "id": 1,
                    "email": "a@test.com",
                    "username": "alice",
                    "first_name": None,
                    "last_name": None,
                    "age": None,
                    "gender": None,
                    "city": None,
                    "is_verified": False,
                    "is_deleted": False,
                    "deleted_at": None,
                },
            )()
        ]

    async def list_for_sync(self, source_ids=None):
        if source_ids:
            return [item for item in self.items if str(item.id) in source_ids]
        return self.items


class EmptyMainRepo:
    async def list_for_sync(self, source_ids=None):
        return []


class FakeDb:
    async def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    @property
    def is_active(self):
        return True

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def execute(self, *args, **kwargs):
        return type("Result", (), {"scalar_one": lambda self: 1})()


def test_sync_user_idempotency_skips_unchanged_payload():
    repo = FakeRepo()
    deps = SyncDependencies(repo, repo, repo, repo, repo, repo, repo)
    main_repos = type("MainRepos", (), {"users": FakeMainUserRepo(), "events": EmptyMainRepo(), "ticket_types": EmptyMainRepo(), "orders": EmptyMainRepo(), "tickets": EmptyMainRepo(), "interactions": EmptyMainRepo()})()
    service = SyncService(FakeDb(), FakeDb(), deps, main_repos)
    result = SyncEntityResult()
    payload = type("MainUser", (), {"id": 1, "email": "a@test.com", "username": "alice", "first_name": None, "last_name": None, "age": None, "gender": None, "city": None, "is_verified": False, "is_deleted": False, "deleted_at": None})()

    asyncio.run(service._sync_user(payload, result))
    asyncio.run(service._sync_user(payload, result))

    assert result.created == 1
    assert result.skipped == 1


def test_sync_batch_uses_main_repositories_as_source_of_truth():
    repo = FakeRepo()
    deps = SyncDependencies(repo, repo, repo, repo, repo, repo, repo)
    main_repos = type("MainRepos", (), {"users": FakeMainUserRepo(), "events": EmptyMainRepo(), "ticket_types": EmptyMainRepo(), "orders": EmptyMainRepo(), "tickets": EmptyMainRepo(), "interactions": EmptyMainRepo()})()
    service = SyncService(FakeDb(), FakeDb(), deps, main_repos)

    result = asyncio.run(service.sync_batch(SyncBatchRequest()))
    assert result.users.created == 1
