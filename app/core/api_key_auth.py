from fastapi import Header, HTTPException, status, Request

from app.core.config import settings


# ---------------------------------------------------------------------
# API Key Authentication Dependency
# ---------------------------------------------------------------------
async def verify_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    """
    Dependency used to secure internal service-to-service communication.
    Ensures only trusted services with valid API key and IP can access routes.
    """

    # 1. Validate presence of API key
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    # 2. Validate correctness of API key
    if x_api_key != settings.CHATBOT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    # 3. IP Allowlist Security Boundary
    client_host = request.client.host
    allowed_ips = settings.CHATBOT_ALLOWED_IPS
    
    if "*" not in allowed_ips and client_host not in allowed_ips:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied from IP: {client_host}",
        )