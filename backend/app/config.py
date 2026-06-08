from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    app_name: str = "JLU Campus Agent API"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: str = "sqlite:///./data/campus_agent.db"
    oa_base_url: str = "https://oa.jlu.edu.cn/"
    oa_crawl_max_pages: int = 50
    oa_crawl_max_details: int = 300
    oa_crawl_months: int = 3
    siliconflow_api_key: str = ""
    siliconflow_embedding_model: str = "Qwen/Qwen3-Embedding-8B"
    embedding_dimensions: int = 1024
    jwt_secret_key: str = "change-me-in-dev"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 7 * 24 * 60
    redis_url: str = "redis://127.0.0.1:6379/0"
    chat_memory_ttl_seconds: int = 3 * 24 * 60 * 60

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
