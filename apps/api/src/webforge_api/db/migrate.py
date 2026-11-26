"""Programmatic Alembic access (migrations ship inside the package)."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

SCRIPT_LOCATION = "webforge_api:migrations"


def alembic_config(sqlalchemy_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", SCRIPT_LOCATION)
    if sqlalchemy_url:
        cfg.attributes["sqlalchemy_url"] = sqlalchemy_url
    return cfg


def upgrade(sqlalchemy_url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(sqlalchemy_url), revision)


def downgrade(sqlalchemy_url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(sqlalchemy_url), revision)
