import uuid
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Optional
from app.db.database import AsyncSessionLocal
from app.core.security import verify_token
from app.core.exceptions import InvalidTokenException, TokenExpiredException

# Dependency setup for JWT
security_scheme = HTTPBearer(auto_error=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to yield an AsyncSession for database operations.
    Relies entirely on `async with` for the safety of closing the session block natively.
    """
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)) -> uuid.UUID:
    """
    Dependency for protected routes.
    Extracts the JWT from the Authorization header and verifies it via TokenService.
    Returns the user id as a uuid.UUID directly.
    """
    if not credentials:
        raise InvalidTokenException("Missing or invalid authorization header.")
        
    try:
        subject = verify_token(credentials.credentials)
        
        # We issued the token specifically based on UUID
        return uuid.UUID(subject)
        
    except ValueError:
        # Failsafe if the subject isn't a valid UUID string
        raise InvalidTokenException("Invalid token subject formatting.")
