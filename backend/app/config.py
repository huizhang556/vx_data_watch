from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VX_", env_file=".env", extra="ignore")

    app_name: str = "视频号数据分析"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/vx_data.db"
    cookie_secure: bool = False
    session_days: int = 14
    max_upload_mb: int = 20
    master_key: str | None = None
    updater_enabled: bool = False
    update_repository: str = "litehub/vx-data-watch"
    update_registry: str = "docker.io"
    update_env_file: Path = Path("/project/.env")
    update_project: str = "vx-data-watch"
    update_service: str = "app"
    registration_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    captcha_enabled: bool = False
    captcha_provider: str = "turnstile"
    captcha_site_key: str | None = None
    captcha_secret_key: str | None = None
    verification_code_minutes: int = 10

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
