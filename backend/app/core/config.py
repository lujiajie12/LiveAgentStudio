from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "LiveAgentStudio"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Database
    DATABASE_URL: Optional[str] = None

    # Redis
    REDIS_URL: Optional[str] = None

    # LLM
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
    DEBUG: bool = True

    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )

    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 60 * 60 * 8

    DATABASE_URL: str = "postgresql://user:password@localhost:5432/liveagent"
    REDIS_URL: str = "redis://localhost:6379/0"
    MILVUS_URL: str = "http://localhost:19530"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str | None = None
    ROUTER_MODEL: str = "gpt-4o-mini"
    ROUTER_TIMEOUT_MS: int = 800
    ROUTER_CONFIDENCE_THRESHOLD: float = 0.6

    SSE_EVENT_DELAY_MS: int = 15
    CHAT_TOKEN_CHUNK_SIZE: int = 12
    MEMORY_WINDOW_SIZE: int = 5

    DEFAULT_DEMO_PASSWORD: str = "demo"
    SENSITIVE_TERMS: List[str] = Field(
        default_factory=lambda: ["最强", "国家级", "包治百病"]
    )


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()
