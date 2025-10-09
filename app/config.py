"""
App configuration via environment variables
Uses pydantic-settings for validation and auto-loading from .env
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import List

# Find the .env file - go up from app/ to project root
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Main app settings - loaded from .env file"""

    # === Database ===
    database_url: str

    # === Redis ===
    redis_url: str = "redis://localhost:6379"

    # === Telegram ===
    telegram_bot_token: str
    telegram_webhook_url: str | None = None  # for production with webhooks

    # === General settings ===
    debug: bool = False
    log_level: str = "INFO"

    # === Check intervals ===
    check_interval_seconds: int = 300  # check bridges every 5 minutes
    alert_cooldown_minutes: int = 30  # don't spam the same alerts

    # === API settings ===
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = ["http://localhost:3000"]

    # === Social monitoring (not implemented yet) ===
    twitter_bearer_token: str | None = None
    discord_webhook_url: str | None = None

    # config for loading from .env file
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),  # absolute path so it works from anywhere
        env_file_encoding="utf-8",
        case_sensitive=False,  # you can write vars in any case
    )


# create global settings instance
settings = Settings()