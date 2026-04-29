from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Chatbot"
    ENV: str = "development"
    DEBUG: bool | str = True

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    CHATBOT_API_KEY: str = ""
    CHATBOT_ALLOWED_IPS: list[str] = ["*"]

    DATABASE_URL: str | None = None
    MAIN_DATABASE_URL: str | None = None
    CHATBOT_DATABASE_URL: str | None = None
    SQL_ECHO: bool = False
    SQL_POOL_PRE_PING: bool = True
    SQL_POOL_RECYCLE: int = 3600
    SQL_POOL_SIZE: int = 10
    SQL_MAX_OVERFLOW: int = 20

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_QUEUE_DB: int = 1

    GEMINI_API_KEY: str
    GEMINI_CONNECT_TIMEOUT_SECONDS: int = 5
    GEMINI_READ_TIMEOUT_SECONDS: int = 30
    GEMINI_MODEL: str = "gemini-1.5-flash"

    ARQ_QUEUE_NAME: str = "chatbot-jobs"
    ARQ_REDIS_SETTINGS_HOST: str | None = None
    ARQ_REDIS_SETTINGS_PORT: int | None = None
    ARQ_REDIS_SETTINGS_DB: int | None = None
    ARQ_REDIS_SETTINGS_PASSWORD: str | None = None
    ARQ_JOB_TIMEOUT_SECONDS: int = 120
    ARQ_MAX_RETRIES: int = 3

    # Rate Limiting
    RATE_LIMIT_FREE: int = 5
    RATE_LIMIT_PREMIUM: int = 20
    RATE_LIMIT_ADMIN: int = 1000
    RATE_LIMIT_WINDOW: int = 60
    RATE_LIMIT_SYSTEM: int = 1000  # Total system-wide requests per window

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def normalize_legacy_settings(self) -> "Settings":
        if isinstance(self.DEBUG, str):
            self.DEBUG = self.DEBUG.strip().lower() in {"1", "true", "yes", "on", "debug", "development"}

        if self.CHATBOT_DATABASE_URL is None and self.DATABASE_URL is not None:
            self.CHATBOT_DATABASE_URL = self.DATABASE_URL
        if self.MAIN_DATABASE_URL is None:
            self.MAIN_DATABASE_URL = self.CHATBOT_DATABASE_URL
        if self.MAIN_DATABASE_URL is None or self.CHATBOT_DATABASE_URL is None:
            raise ValueError("MAIN_DATABASE_URL and CHATBOT_DATABASE_URL must be configured, or provide legacy DATABASE_URL.")

        if self.ARQ_REDIS_SETTINGS_HOST is None:
            self.ARQ_REDIS_SETTINGS_HOST = self.REDIS_HOST
        if self.ARQ_REDIS_SETTINGS_PORT is None:
            self.ARQ_REDIS_SETTINGS_PORT = self.REDIS_PORT
        if self.ARQ_REDIS_SETTINGS_DB is None:
            self.ARQ_REDIS_SETTINGS_DB = self.REDIS_QUEUE_DB
        if self.ARQ_REDIS_SETTINGS_PASSWORD is None:
            self.ARQ_REDIS_SETTINGS_PASSWORD = self.REDIS_PASSWORD
        return self


settings = Settings()
