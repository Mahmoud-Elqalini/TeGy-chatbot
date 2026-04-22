


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
    def __init__(self, detail: str = "Invalid token"):
        super().__init__(401, detail)

class TokenExpiredException(AppException):
    def __init__(self, detail: str = "Token has expired"):
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


# ─── Message ──────────────────────────────────────────────────────────────────
class MessageNotFoundException(AppException):
    def __init__(self, detail: str = "Message not found"):
        super().__init__(404, detail)


# ─── AI ───────────────────────────────────────────────────────────────────────
class AIException(AppException):
    def __init__(self, detail: str = "AI service error"):
        super().__init__(502, detail)

class AITimeoutException(AIException):
    def __init__(self, detail: str = "AI service connection timed out"):
        super().__init__(detail)

class AITransientException(AIException):
    def __init__(self, detail: str = "AI service transient error"):
        super().__init__(detail)

class LLMUnavailableException(AIException):
    def __init__(self, detail: str = "LLM exhausted retries or is completely unreachable"):
        super().__init__(detail)


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

