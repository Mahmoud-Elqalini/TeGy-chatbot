import jwt
from app.core.config import settings
from app.core.exceptions import InvalidTokenException, TokenExpiredException


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
