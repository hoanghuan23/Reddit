from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/reddit.db"
    lookback_hours: int = 24
    request_timeout_seconds: int = 30
    max_posts_per_source: int = 100
    metrics_update_batch_size: int = 25
    metrics_request_delay_seconds: float = 0.75
    cookie_cache_ttl_seconds: int = 12 * 60 * 60
    reddit_user_agent: str = "linux:reddit-crawler:v1.0"
    scheduler_poll_seconds: int = 60
    scheduler_enabled: bool = True
    reddit_max_retries: int = 2
    reddit_retry_backoff_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
