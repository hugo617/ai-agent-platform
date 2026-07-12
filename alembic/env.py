"""Alembic migration environment.

Reads the database URL from our Pydantic settings (instead of alembic.ini) so a
single ``.env`` controls everything. Imports ``Base.metadata`` to enable
``--autogenerate``.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.core.database import Base

# Import every module that defines models so they register on Base.metadata.
from app.models import (  # noqa: F401
    agent,
    api_token,
    llm_config,
    log,
    message,
    rbac,
    security,
    tenant,
)

config = context.config
# Alembic runs migrations via a *sync* connection, so normalise the runtime
# (async) DATABASE_URL to its sync driver equivalent:
#   postgresql+psycopg://...  -> postgresql+psycopg://...  (already sync)
#   postgresql://...          -> postgresql+psycopg://...
#   sqlite+aiosqlite://...    -> sqlite://...              (sync pysqlite)
# Leaving an async URL here makes engine_from_config() fail at connect time.
sync_url = settings.database_url.replace("sqlite+aiosqlite://", "sqlite://")
sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://")
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables managed by external libraries (not by our migrations). Without this,
# alembic autogenerate tries to drop them on every run because they are not on
# Base.metadata.
_EXCLUDED_TABLES = {"casbin_rule"}
include_object = lambda obj, name, type_, reflected, compare_to: (  # noqa: E731
    type_ != "table" or name not in _EXCLUDED_TABLES
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
