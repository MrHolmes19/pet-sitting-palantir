"""Runtime configuration helpers."""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Settings:
    """Environment-backed application settings."""

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        supabase_url=getenv("SUPABASE_URL"),
        supabase_service_role_key=getenv("SUPABASE_SERVICE_ROLE_KEY"),
        database_url=getenv("DATABASE_URL"),
        telegram_bot_token=getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=getenv("TELEGRAM_CHAT_ID"),
    )
