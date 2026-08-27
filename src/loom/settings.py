"""Environment-backed settings for secrets used by Loom."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretSettings(BaseSettings):
    """Secrets loaded only from the environment or an ignored local env file."""

    model_config = SettingsConfigDict(
        env_file=Path(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str | None = None
