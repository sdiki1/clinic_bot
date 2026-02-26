from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    manager_chat_id: int = Field(alias="MANAGER_CHAT_ID")

    clinic_site_url: str = Field(alias="CLINIC_SITE_URL")
    loyalty_bot_username: str = Field(alias="LOYALTY_BOT_USERNAME")
    loyalty_start_prefix: str = Field(default="user_", alias="LOYALTY_START_PREFIX")

    database_url: str = Field(
        default="postgresql+asyncpg://marulidi:marulidi_password@localhost:5123/marulidi_bot",
        alias="DATABASE_URL",
    )

    guide_instagram_path: Path | None = Field(default=None, alias="GUIDE_INSTAGRAM_PATH")
    guide_youtube_path: Path | None = Field(default=None, alias="GUIDE_YOUTUBE_PATH")
    guide_default_path: Path | None = Field(default=None, alias="GUIDE_DEFAULT_PATH")

    phone_hash_salt: str = Field(alias="PHONE_HASH_SALT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("loyalty_bot_username")
    @classmethod
    def normalize_bot_username(cls, value: str) -> str:
        return value.strip().lstrip("@")

    @field_validator("phone_hash_salt")
    @classmethod
    def validate_salt(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("PHONE_HASH_SALT must be at least 8 characters")
        return cleaned


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
