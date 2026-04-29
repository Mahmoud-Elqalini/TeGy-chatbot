import uuid
from fastapi import Depends, Header, Request, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.exceptions import InvalidTokenException
from app.core.security import verify_token
from app.core.auth_context import AuthContext, AuthMode
from app.core.api_key_auth import verify_api_key

security_scheme = HTTPBearer(auto_error=False)


class CurrentActor(BaseModel):
    subject: str
    user_id: uuid.UUID | None = None
    user_source_id: str | None = None


async def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> CurrentActor:
    if not credentials:
        raise InvalidTokenException("Missing or invalid authorization header.")

    subject = verify_token(credentials.credentials)
    actor = CurrentActor(subject=subject)
    try:
        actor.user_id = uuid.UUID(subject)
    except ValueError:
        actor.user_source_id = subject
    return actor


async def get_current_user(actor: CurrentActor = Depends(get_current_actor)) -> uuid.UUID:
    if actor.user_id is None:
        raise InvalidTokenException("Token subject must be a valid UUID for this endpoint.")
    return actor.user_id


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    x_api_key: str | None = Header(default=None),
) -> AuthContext:
    """
    Unified authentication dependency supporting both JWT and API Key.
    """
    # 1. Try API Key (Integration Mode)
    if x_api_key:
        await verify_api_key(request, x_api_key)
        
        try:
            body = await request.json()
            user_id = body.get("user_id")
            if not user_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required in body for API Key authentication.")
            
            return AuthContext(
                mode=AuthMode.INTEGRATION,
                user_id=uuid.UUID(user_id),
                is_trusted=True
            )
        except Exception as e:
            if isinstance(e, HTTPException): raise e
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body for identity resolution.")

    # 2. Try JWT (User Mode)
    if credentials:
        subject = verify_token(credentials.credentials)
        try:
            return AuthContext(
                mode=AuthMode.USER,
                user_id=uuid.UUID(subject)
            )
        except ValueError:
            return AuthContext(
                mode=AuthMode.USER,
                user_id=uuid.uuid4(), 
                user_source_id=subject
            )

    raise InvalidTokenException("Missing or invalid authentication credentials (JWT or API Key).")
