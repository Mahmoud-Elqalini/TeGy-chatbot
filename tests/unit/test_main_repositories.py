import asyncio

from app.db.main_repositories import MainRepositoryBundle, build_main_repository_bundle


class FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class FakeSession:
    def __init__(self, values):
        self.values = values

    async def execute(self, statement):
        return FakeResult(self.values)


def test_build_main_repository_bundle_returns_all_repositories():
    bundle = build_main_repository_bundle(FakeSession([]))
    assert isinstance(bundle, MainRepositoryBundle)
    assert bundle.users is not None
    assert bundle.events is not None


def test_main_user_repository_list_for_sync_executes_query():
    bundle = build_main_repository_bundle(FakeSession([1, 2]))
    result = asyncio.run(bundle.users.list_for_sync({"1", "2"}))
    assert result == [1, 2]
