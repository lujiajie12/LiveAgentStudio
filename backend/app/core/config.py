from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Optional
from functools import lru_cache
import os


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "LiveAgentStudio"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "off", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "on", "yes"}:
                return True
        return value

    # 存为字符串，在 property 里解析，避免 pydantic-settings 提前 json.loads
    CORS_ORIGINS_STR: str = "http://localhost:3000,http://localhost:5173"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [i.strip() for i in self.CORS_ORIGINS_STR.split(',') if i.strip()]

    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 60 * 60 * 8

    DATABASE_URL: str = "postgresql://user:password@localhost:5432/liveagent"
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    ROUTER_MODEL: str = "qwen-plus"
    ROUTER_TIMEOUT_MS: int = 5000
    ROUTER_CONFIDENCE_THRESHOLD: float = 0.6

    # Milvus
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530

    # Elasticsearch BM25
    ES_HOST: str = "localhost"
    ES_PORT: int = 9200

    # BGE 本地嵌入模型
    EMBEDDING_MODEL: str = "G:/LLM/Local_model/BAAI/bge-large-zh-v1___5"
    EMBEDDING_DIM: int = 1024
    EMBEDDING_DEVICE: str = "cuda"
    EMBEDDING_BATCH_SIZE: int = 64

    # 阿里百炼 Reranker (gte-rerank)
    DASHSCOPE_API_KEY: Optional[str] = None

    SSE_EVENT_DELAY_MS: int = 15
    CHAT_TOKEN_CHUNK_SIZE: int = 12
    MEMORY_WINDOW_SIZE: int = 5

    DEFAULT_DEMO_PASSWORD: str = "demo"
    SENSITIVE_TERMS: List[str] = Field(
        default_factory=lambda: ["最强", "国家级", "包治百病"]
    )


@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()
