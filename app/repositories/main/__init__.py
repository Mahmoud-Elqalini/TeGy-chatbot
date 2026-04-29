from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.main.event_repo import MainEventRepository
from app.repositories.main.user_repo import MainUserRepository

@dataclass
class MainRepositoryBundle:
    users: MainUserRepository
    events: MainEventRepository

def build_main_repository_bundle(session: AsyncSession) -> MainRepositoryBundle:
    return MainRepositoryBundle(
        users=MainUserRepository(session),
        events=MainEventRepository(session),
    )
