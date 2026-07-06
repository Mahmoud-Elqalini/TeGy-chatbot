from __future__ import annotations
from typing import Any, List, Optional, Union
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Chatbot"
    ENV: str = "development"
    DEBUG: Union[bool, str] = True

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    CHATBOT_API_KEY: str = ""
    CHATBOT_ALLOWED_IPS: List[str] = ["*"]

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # API Versioning
    API_VERSION: str = "1.0.0"

    # External Services
    SEMANTIC_SEARCH_API_URL: str = "http://138.197.63.199:8000/search"

    # Semantic Cache Settings
    SEMANTIC_CACHE_THRESHOLD: float = 0.88
    SEMANTIC_CACHE_TTL_DAYS: int = 7

    DATABASE_URL: Optional[str] = None
    MAIN_DATABASE_URL: Optional[str] = None
    CHATBOT_DATABASE_URL: Optional[str] = None
    DATABASE_URL_CHATBOT: Optional[str] = None  # Added to support Neon DB naming
    SQL_ECHO: bool = False
    SQL_POOL_PRE_PING: bool = True
    SQL_POOL_RECYCLE: int = 1800  # Reduced to 30 minutes for better cloud compatibility
    SQL_POOL_SIZE: int = 10
    SQL_MAX_OVERFLOW: int = 20

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_QUEUE_DB: int = 0
    REDIS_SSL: bool = False

    GEMINI_API_KEY: str
    GEMINI_CONNECT_TIMEOUT_SECONDS: int = 5
    GEMINI_READ_TIMEOUT_SECONDS: int = 30
    GEMINI_MODEL: str = "gemini-3-flash-preview"

    # Global AI Settings
    AI_TEMPERATURE: float = 0.3
    AI_MAX_TOKENS: int = 4096

    # Resilience Settings
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BASE_DELAY: float = 0.5
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 30
    HTTP_MAX_CONNECTIONS: int = 10
    HTTP_MAX_KEEPALIVE: int = 5

    # Groq Fallback
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TIMEOUT_SECONDS: int = 30

    # Fireworks Fallback
    FIREWORKS_API_KEY: str = ""
    FIREWORKS_BASE_URL: str = "https://api.fireworks.ai/inference/v1"
    FIREWORKS_MODEL: str = "accounts/fireworks/models/qwen-v2p5-14b-instruct"
    FIREWORKS_TIMEOUT_SECONDS: int = 30



    ARQ_QUEUE_NAME: str = "chatbot-jobs"
    ARQ_REDIS_SETTINGS_HOST: Optional[str] = None
    ARQ_REDIS_SETTINGS_PORT: Optional[int] = None
    ARQ_REDIS_SETTINGS_DB: Optional[int] = None
    ARQ_REDIS_SETTINGS_PASSWORD: Optional[str] = None
    ARQ_JOB_TIMEOUT_SECONDS: int = 120
    ARQ_MAX_RETRIES: int = 3

    # Timeouts
    AI_REQUEST_TIMEOUT: int = 45
    CHAT_MAX_HISTORY: int = 5
    REDIS_OPERATION_TIMEOUT: int = 3
    DB_OPERATION_TIMEOUT: int = 5

    # Rate Limiting
    RATE_LIMIT_FREE: int = 5
    RATE_LIMIT_PREMIUM: int = 20
    RATE_LIMIT_ADMIN: int = 1000
    RATE_LIMIT_WINDOW: int = 60
    RATE_LIMIT_SYSTEM: int = 1000  # Total system-wide requests per window

    # ── AI PROMPTS ────────────────────────────────────────────────────────
    # Prompts are now managed via app/ai/prompt_loader.py and stored in app/ai/prompts/

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def normalize_legacy_settings(self) -> "Settings":
        if isinstance(self.DEBUG, str):
            self.DEBUG = self.DEBUG.strip().lower() in {"1", "true", "yes", "on", "debug", "development"}

        # 1. Prioritize DATABASE_URL_CHATBOT (Neon) or CHATBOT_DATABASE_URL
        if self.CHATBOT_DATABASE_URL is None:
            self.CHATBOT_DATABASE_URL = self.DATABASE_URL_CHATBOT or self.DATABASE_URL

        # 2. Fallback for MAIN_DATABASE_URL
        if self.MAIN_DATABASE_URL is None:
            self.MAIN_DATABASE_URL = self.CHATBOT_DATABASE_URL

        # 3. Normalize both URLs for asyncpg compatibility
        for attr in ["MAIN_DATABASE_URL", "CHATBOT_DATABASE_URL"]:
            url = getattr(self, attr)
            if url and isinstance(url, str):
                # Fix scheme for Postgres
                if url.startswith("postgresql://"):
                    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
                
                # Clean query parameters ONLY for postgresql/asyncpg compatibility
                if "?" in url and "postgresql" in url:
                    base_url, query_params = url.split("?", 1)
                    # Check if SSL is required (Neon usually has sslmode=require)
                    is_ssl = any(p in query_params for p in ["sslmode=require", "ssl=require", "ssl=true"])
                    # Rebuild URL without problematic sync params
                    url = f"{base_url}?ssl=require" if is_ssl else base_url
                
                setattr(self, attr, url)

        if self.MAIN_DATABASE_URL is None or self.CHATBOT_DATABASE_URL is None:
            raise ValueError("MAIN_DATABASE_URL and CHATBOT_DATABASE_URL must be configured, or provide legacy DATABASE_URL.")

        # 4. Clean REDIS_HOST (Upstash sometimes provides URLs, but we need only the hostname)
        if self.REDIS_HOST and isinstance(self.REDIS_HOST, str):
            # Auto-enable SSL for Upstash or Production
            if "upstash.io" in self.REDIS_HOST.lower() or self.ENV.lower() == "production":
                self.REDIS_SSL = True

            for prefix in ["https://", "http://", "redis://", "rediss://"]:
                if self.REDIS_HOST.startswith(prefix):
                    self.REDIS_HOST = self.REDIS_HOST.replace(prefix, "", 1)
            # Remove trailing slashes or ports if they were included in the host string
            if "/" in self.REDIS_HOST:
                self.REDIS_HOST = self.REDIS_HOST.split("/")[0]
            if ":" in self.REDIS_HOST:
                # If there's a colon, check if it's just the port and strip it (we use REDIS_PORT)
                host_parts = self.REDIS_HOST.split(":")
                if host_parts[-1].isdigit():
                    self.REDIS_HOST = ":".join(host_parts[:-1])

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
