import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from app.core.config import settings
from app.core.exceptions import TokenExpiredException, InvalidTokenException

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a JWT access token for the given subject (usually a user_id or username).
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> str:
    """
    Verifies a JWT token and returns the subject (str) if valid. 
    Raises TokenExpiredException if expired.
    Raises InvalidTokenException if invalid.
    """
    try:
        decoded_data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = decoded_data.get("sub")
        if not sub:
            raise InvalidTokenException()
        return sub
    except jwt.ExpiredSignatureError:
        raise TokenExpiredException()
    except jwt.PyJWTError:
        raise InvalidTokenException()
