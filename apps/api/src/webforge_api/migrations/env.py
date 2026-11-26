"""Alembic environment. The database URL comes from validated settings, never alembic.ini."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

import webforge_api.models  # noqa: F401  (populate metadata)
from webforge_api.db.base import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.attributes.get("sqlalchemy_url")
    if url is None:
        from webforge_api.config import get_settings

        url = get_settings().sqlalchemy_url
    return str(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
