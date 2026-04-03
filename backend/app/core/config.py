from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = BACKEND_ROOT / ".env"


class AppSettings(BaseSettings):
    """统一的后端运行时配置。

    约束说明：
    1. 应用运行时只读取 `backend/.env` 和进程环境变量。
    2. `deploy/.env` 只服务于 Docker Compose，不再被业务代码兜底读取。
    3. 所有可调参数都集中在这里声明，README 和 `.env.example` 也以这里为准。
    """

    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
    )

    # 基础应用配置
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

    # CORS 与认证
    CORS_ORIGINS_STR: str = "http://localhost:3000,http://localhost:5173"
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 60 * 60 * 8
    DEFAULT_DEMO_PASSWORD: str = "demo"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [item.strip() for item in self.CORS_ORIGINS_STR.split(",") if item.strip()]

    # 基础设施连接
    DATABASE_URL: str = "postgresql://root:change_me@localhost:5432/liveagent"
    REDIS_URL: str = "redis://localhost:6379/0"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    ES_HOST: str = "localhost"
    ES_PORT: int = 9200

    # LLM / Router / Planner
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    ROUTER_MODEL: str = "qwen-plus"
    ROUTER_TIMEOUT_MS: int = 5000
    PLANNER_MODEL: Optional[str] = None
    PLANNER_TIMEOUT_MS: int = 6000
    PLANNER_MAX_STEPS: int = 4
    ROUTER_CONFIDENCE_THRESHOLD: float = 0.6

    # Web 搜索
    SERPAPI_API_KEY: Optional[str] = None
    SERPAPI_BASE_URL: str = "https://serpapi.com/search.json"
    SERPAPI_ENGINE: str = "google"
    SERPAPI_GL: str = "cn"
    SERPAPI_HL: str = "zh-cn"
    SERPAPI_NUM_RESULTS: int = 5
    SERPAPI_TIMEOUT_SECONDS: float = 15.0

    # 长期记忆
    MEM0_API_KEY: Optional[str] = None
    MEM0_BASE_URL: Optional[str] = None
    MEM0_ORG_ID: Optional[str] = None
    MEM0_PROJECT_ID: Optional[str] = None
    QA_MEMORY_ENABLED: bool = False
    QA_MEMORY_AGENT_ID: str = "qa_agent"
    QA_MEMORY_APP_ID: str = "liveagent-studio"
    QA_MEMORY_TOP_K: int = 4
    QA_MEMORY_THRESHOLD: float = 0.45
    QA_MEMORY_RECALL_DEFAULT_LIMIT: int = 3
    QA_MEMORY_RECALL_MAX_ITEMS: int = 5

    # RAG / Embedding / Milvus
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DIM: int = 1024
    EMBEDDING_DEVICE: str = "cuda"
    EMBEDDING_BATCH_SIZE: int = 64
    MILVUS_INDEX_FLUSH_INTERVAL_CHUNKS: int = 1024
    MILVUS_RESET_SETTLE_SECONDS: int = 15
    DASHSCOPE_API_KEY: Optional[str] = None

    # Reranker
    RERANKER_MODEL: str = "/Volumes/App/LocalModel/BAAI/bge-reranker-v2-m3"
    RERANKER_DEVICE: str = "mps"
    USE_LOCAL_RERANKER: bool = True

    # 流式输出与观测
    SSE_EVENT_DELAY_MS: int = 25
    CHAT_TOKEN_CHUNK_SIZE: int = 6
    # 这里按“消息条数”裁剪短期记忆，而不是按“问答轮数”。
    MEMORY_WINDOW_SIZE: int = 12
    MEMORY_TTL_SECONDS: int = 7200
    HOT_KEYWORDS_TTL_SECONDS: int = 120
    HIGH_FREQUENCY_QUESTION_LIMIT: int = 5
    METRICS_LOG_SAMPLE_LIMIT: int = 500
    OFFLINE_JOB_LOG_LINES: int = 60

    # 风控词默认值支持直接启动，也允许通过 env 用 JSON 或逗号分隔覆盖。
    SENSITIVE_TERMS: List[str] = Field(
        default_factory=lambda: ["最强", "国家级", "包治百病"]
    )

    @field_validator("SENSITIVE_TERMS", mode="before")
    @classmethod
    def parse_sensitive_terms(cls, value):
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            if normalized.startswith("["):
                return value
            return [item.strip() for item in normalized.split(",") if item.strip()]
        return value


@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()
