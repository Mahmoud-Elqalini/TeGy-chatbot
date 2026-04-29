from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chatbot.base import ChatbotBase as Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: AsyncSession, id_field: str = "id"):
        self.model = model
        self.db = db
        self.id_field = id_field

    async def get(self, id: Any) -> Optional[ModelType]:
        query = select(self.model).filter(getattr(self.model, self.id_field) == id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100, order_by: Any = None) -> List[ModelType]:
        query = select(self.model)
        if order_by is not None:
            query = query.order_by(order_by)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, obj_in: dict[str, Any], commit: bool = True) -> ModelType:
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        try:
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
            await self.db.refresh(db_obj)
        except Exception:
            await self.db.rollback()
            raise
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: dict[str, Any], commit: bool = True) -> ModelType:
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        try:
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
            await self.db.refresh(db_obj)
        except Exception:
            await self.db.rollback()
            raise
        return db_obj

    async def delete(self, id: Any, commit: bool = True) -> bool:
        query = select(self.model).filter(getattr(self.model, self.id_field) == id)
        result = await self.db.execute(query)
        db_obj = result.scalar_one_or_none()
        if db_obj is None:
            return False

        try:
            await self.db.delete(db_obj)
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except Exception:
            await self.db.rollback()
            raise
        return True
