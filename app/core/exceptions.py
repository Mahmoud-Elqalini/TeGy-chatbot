class AppException(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str | None = None):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code or self.__class__.__name__.replace("Exception", "").upper()


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(401, detail, "UNAUTHORIZED")


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Access denied"):
        super().__init__(403, detail, "FORBIDDEN")


class InvalidTokenException(AppException):
    def __init__(self, detail: str = "Invalid token"):
        super().__init__(401, detail, "INVALID_TOKEN")


class TokenExpiredException(AppException):
    def __init__(self, detail: str = "Token has expired"):
        super().__init__(401, detail, "TOKEN_EXPIRED")


class UserNotFoundException(AppException):
    def __init__(self, detail: str = "User not found"):
        super().__init__(404, detail, "USER_NOT_FOUND")


class UserAlreadyExistsException(AppException):
    def __init__(self, detail: str = "User already exists"):
        super().__init__(409, detail, "USER_ALREADY_EXISTS")


class SessionNotFoundException(AppException):
    def __init__(self, detail: str = "Session not found"):
        super().__init__(404, detail, "SESSION_NOT_FOUND")


class MessageNotFoundException(AppException):
    def __init__(self, detail: str = "Message not found"):
        super().__init__(404, detail, "MESSAGE_NOT_FOUND")


class NotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(404, detail, "NOT_FOUND")


class ValidationException(AppException):
    def __init__(self, detail: str = "Validation error"):
        super().__init__(422, detail, "VALIDATION_ERROR")


class RateLimitException(AppException):
    def __init__(self, detail: str = "Too many requests. Please try again later.", retry_after: int = 60):
        super().__init__(429, detail, "RATE_LIMIT_EXCEEDED")
        self.retry_after = retry_after


class AIException(AppException):
    def __init__(self, detail: str = "AI service error", error_code: str = "AI_ERROR"):
        super().__init__(502, detail, error_code)


class AITimeoutException(AIException):
    def __init__(self, detail: str = "AI service connection timed out"):
        super().__init__(detail, "AI_TIMEOUT")


class AITransientException(AIException):
    def __init__(self, detail: str = "AI service transient error"):
        super().__init__(detail, "AI_TRANSIENT")


class LLMUnavailableException(AIException):
    def __init__(self, detail: str = "LLM unreachable or exhausted retries"):
        super().__init__(detail, "LLM_UNAVAILABLE")
