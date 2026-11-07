from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MEDSPACED_",
        extra="ignore",
    )

    app_name: str = "MedSpaced"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    secret_key: str = "dev-only-secret-change-in-production"
    access_token_minutes: int = 60
    refresh_token_days: int = 14

    database_url: str = "sqlite:///./var/medspaced.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800
    storage_dir: str = "./var/storage"

    llm_provider: str = "fake"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 90
    embedding_model: str = "text-embedding-3-small"

    mastery_threshold: float = 70.0
    daily_new_card_limit: int = 20
    irt_model: Literal["2pl", "3pl", "mirt"] = "mirt"
    srs_algorithm: Literal["sm2", "fsrs"] = "fsrs"
    vignette_llm_eval: bool = True
    vignette_pass_score: float = 0.65
    fsrs_optimizer_enabled: bool = True
    fsrs_optimizer_min_reviews: int = 512
    max_upload_mb: int = 50
    max_chunks_per_generation: int = 40

    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    job_queue_backend: Literal["inline", "celery"] = "inline"
    trust_proxy_headers: bool = False
    trusted_proxies: str = ""
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    metrics_enabled: bool = True
    metrics_token: str = ""
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "medspaced-api"

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


_WEAK_SECRETS = {
    "",
    "dev-only-secret-change-in-production",
    "change-me-to-a-long-random-string",
    "change-me-in-production",
}


def validate_runtime_settings(config: Settings | None = None) -> None:
    config = config or settings
    if config.environment.lower() not in {"production", "prod"}:
        return
    if config.secret_key in _WEAK_SECRETS or len(config.secret_key) < 32:
        raise RuntimeError(
            "Üretimde MEDSPACED_SECRET_KEY en az 32 karakterlik güçlü bir değer olmalıdır"
        )
    if "*" in config.origins:
        raise RuntimeError("Üretimde MEDSPACED_ALLOWED_ORIGINS joker karakter içeremez")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
