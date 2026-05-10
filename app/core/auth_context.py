from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
import uuid
import enum
from pydantic import BaseModel


class AuthMode(str, enum.Enum):
    USER = "USER"
    INTEGRATION = "INTEGRATION"


class AuthContext(BaseModel):
    """
    Unified authentication context that carries identity and source information.
    """
    mode: AuthMode
    user_id: uuid.UUID
    user_source_id: Optional[str] = None
    is_trusted: bool = False