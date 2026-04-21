from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# ═══════════════════════════════════════════════════════════════════════════════
#  Custom Exceptions
# ═══════════════════════════════════════════════════════════════════════════════

class AppException(Exception):
    """Base exception for all app errors"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


# ─── Auth ─────────────────────────────────────────────────────────────────────
class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(401, detail)

class ForbiddenException(AppException):
    def __init__(self, detail: str = "Access denied"):
        super().__init__(403, detail)

class InvalidTokenException(AppException):
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(401, detail)


# ─── User ─────────────────────────────────────────────────────────────────────
class UserNotFoundException(AppException):
    def __init__(self, detail: str = "User not found"):
        super().__init__(404, detail)

class UserAlreadyExistsException(AppException):
    def __init__(self, detail: str = "Email or username already exists"):
        super().__init__(409, detail)

class InvalidCredentialsException(AppException):
    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(401, detail)


# ─── Session ──────────────────────────────────────────────────────────────────
class SessionNotFoundException(AppException):
    def __init__(self, detail: str = "Session not found"):
        super().__init__(404, detail)


# ─── AI ───────────────────────────────────────────────────────────────────────
class AIException(AppException):
    def __init__(self, detail: str = "AI service error"):
        super().__init__(502, detail)


# ─── General ──────────────────────────────────────────────────────────────────
class NotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(404, detail)

class ValidationException(AppException):
    def __init__(self, detail: str = "Validation error"):
        super().__init__(422, detail)

class RateLimitException(AppException):
    def __init__(self, detail: str = "Too many requests"):
        super().__init__(429, detail)


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
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )