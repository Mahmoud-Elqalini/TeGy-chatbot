import importlib
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeSession:
    async def execute(self, *args, **kwargs):
        return self

    def scalar_one(self):
        return 1

    def scalar_one_or_none(self):
        return None


class FakeRedis:
    async def exists(self, key: str) -> bool:
        return False


@pytest.fixture
def client(monkeypatch):
    main = importlib.import_module("main")
    deps = importlib.import_module("app.api.v1.dependencies")

    async def override_chatbot():
        yield FakeSession()

    async def override_main():
        yield FakeSession()

    async def override_redis():
        return FakeRedis()

    main.app.dependency_overrides[deps.get_chatbot_session] = override_chatbot
    main.app.dependency_overrides[deps.get_main_session] = override_main
    monkeypatch.setattr("app.api.v1.routes.health.get_redis", override_redis)

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()
