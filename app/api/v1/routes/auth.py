from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Any

from app.api.v1.dependencies import get_db
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.core.security import create_access_token
from app.schemas.user import UserRead, UserCreate, UserLogin

router = APIRouter(prefix="/auth", tags=["Authentication"])

# OAuth2 compliant token response (no user object here typically, but we can extend it or use TokenResponse if we want, but OAuth2 UI expects just access_token and token_type)
class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str

@router.post("/register", response_model=UserRead)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user with email and password.
    """
    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo)
    return await auth_service.register_user(user_in)

@router.post("/login", response_model=OAuth2TokenResponse)
async def login(
    user_in: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email and password (JSON body), returns a JWT access token.
    """
    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo)
    
    user = await auth_service.authenticate_user(user_in)
    access_token = create_access_token(subject=str(user.user_id))
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }
