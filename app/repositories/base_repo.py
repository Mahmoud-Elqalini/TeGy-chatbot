from typing import Generic, TypeVar, Type, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: AsyncSession, id_field: str = "id"):
        """
        Base CRUD object with default methods to Create, Read, Update, Delete (CRUD).
        """
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
        # return list instead of sequence pattern
        return list(result.scalars().all())

    async def create(self, obj_in: dict[str, Any]) -> ModelType:
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        try:
            await self.db.commit()
            await self.db.refresh(db_obj)
        except Exception:
            await self.db.rollback()
            raise
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: dict[str, Any]) -> ModelType:
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        try:
            await self.db.commit()
            await self.db.refresh(db_obj)
        except Exception:
            await self.db.rollback()
            raise
        return db_obj

    async def delete(self, id: Any) -> bool:
        query = select(self.model).filter(getattr(self.model, self.id_field) == id)
        result = await self.db.execute(query)
        db_obj = result.scalar_one_or_none()
        
        if db_obj:
            try:
                await self.db.delete(db_obj)
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise
            return True
        return False
