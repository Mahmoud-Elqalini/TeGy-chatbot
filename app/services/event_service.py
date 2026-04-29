from app.repositories.main.event_repo import MainEventRepository
from app.models.main.event import Event

class EventService:
    def __init__(self, main_event_repo: MainEventRepository):
        self.main_event_repo = main_event_repo

    async def get_by_source_id(self, source_id: int) -> Event | None:
        return await self.main_event_repo.get_by_source_id(source_id)

    async def search_events(self, query: str, limit: int = 5) -> list[Event]:
        return await self.main_event_repo.search_events(query, limit)
