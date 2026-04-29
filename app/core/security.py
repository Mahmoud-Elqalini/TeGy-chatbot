from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenException, TokenExpiredException


def create_access_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"exp": expire, "sub": str(subject)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> str:
    try:
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        subject = decoded.get("sub")
        if not subject:
            raise InvalidTokenException()
        return subject
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredException() from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenException() from exc
