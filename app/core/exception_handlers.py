import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.exceptions import AppException, RateLimitException
from app.core.observability import get_trace_id

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register unified exception handlers."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(
            "app-exception path=%s status=%s detail=%s request_id=%s",
            request.url.path,
            exc.status_code,
            exc.detail,
            get_trace_id(),
        )
        headers = {}
        if isinstance(exc, RateLimitException):
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.detail
                },
                "request_id": get_trace_id()
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "validation-error path=%s error=%s request_id=%s",
            request.url.path,
            exc.errors(),
            get_trace_id(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The request payload is invalid.",
                    "details": exc.errors()
                },
                "request_id": get_trace_id()
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled-exception method=%s path=%s error_type=%s error=%s request_id=%s",
            request.method,
            request.url.path,
            type(exc).__name__,
            exc,
            get_trace_id(),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred."
                },
                "request_id": get_trace_id()
            },
        )
