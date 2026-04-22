import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  Register Handlers on the FastAPI app
# ═══════════════════════════════════════════════════════════════════════════════

def register_exception_handlers(app: FastAPI) -> None:
    """It is called in main.py once"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        # Log the real error so we can debug it
        logger.error(f"Unhandled exception on {request.method} {request.url}: {type(exc).__name__}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

