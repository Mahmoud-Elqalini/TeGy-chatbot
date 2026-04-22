from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Application Config
    PROJECT_NAME: str = "AI Chatbot"
    ENV: str = "development"
    DEBUG: bool = True

    # Security Config
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # Database Config
    DATABASE_URL: str

    # Redis Config
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # Gemini Config
    GEMINI_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()