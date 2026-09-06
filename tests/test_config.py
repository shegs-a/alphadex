"""Unit tests for configuration resolution."""

from __future__ import annotations

from alphadex.config import Settings


def test_sqlalchemy_url_assembled_from_postgres_parts() -> None:
    settings = Settings(
        database_url=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@h:1234/d"


def test_explicit_database_url_takes_precedence() -> None:
    settings = Settings(
        database_url="sqlite:///custom.db",
        postgres_user="ignored",
    )
    assert settings.sqlalchemy_url == "sqlite:///custom.db"
