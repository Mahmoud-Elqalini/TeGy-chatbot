from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserRead, UserCreate, UserLogin
from app.core.security import get_password_hash, verify_password

class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def register_user(self, user_in: UserCreate) -> UserRead:
        """
        Registers a new user with email and hashed password.
        """
        existing_user = await self.user_repo.get_by_email(user_in.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_pw = get_password_hash(user_in.password)
        user_data = {
            "name": user_in.name,
            "email": user_in.email,
            "hashed_password": hashed_pw
        }
        user_obj = await self.user_repo.create(user_data)
        return UserRead.model_validate(user_obj)

    async def authenticate_user(self, user_in: UserLogin) -> UserRead:
        """
        Authenticates a user by checking email and password.
        """
        user_obj = await self.user_repo.get_by_email(user_in.email)
        if not user_obj:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not verify_password(user_in.password, user_obj.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return UserRead.model_validate(user_obj)
