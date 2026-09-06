"""Application configuration.

Env-driven via pydantic-settings (AGENTS.md §12, ADR-002). No secrets are
hard-coded; see ``.env.example`` for the documented set. ``DATABASE_URL`` may be
provided directly, or assembled from the individual ``POSTGRES_*`` variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = Field(default="local", description="local | staging | production")
    app_log_level: str = Field(default="INFO")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    # ── Database ─────────────────────────────────────────────────────────────
    # Either set DATABASE_URL directly, or the POSTGRES_* parts below.
    database_url: str | None = Field(default=None)
    postgres_user: str = Field(default="alphadex")
    postgres_password: str = Field(default="alphadex")
    postgres_db: str = Field(default="alphadex")
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        """Resolved SQLAlchemy URL: explicit DATABASE_URL wins, else assembled."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (one read of the environment)."""
    return Settings()
