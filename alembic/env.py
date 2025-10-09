"""
Alembic setup for migrations
Connects to DB and configures auto-generation
"""

import sys
from pathlib import Path

# add project root to PYTHONPATH so imports work
sys.path.append(str(Path(__file__).parent.parent))

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# import our models and config
from app.core.database import Base
from app.config import settings
import app.models  # this imports all models

# Alembic config
config = context.config

# setup logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# model metadata for auto-generation
target_metadata = Base.metadata

# fix Render's database URL for async driver
database_url = settings.database_url.replace(
    "postgresql://",
    "postgresql+asyncpg://"
)

# set database URL from our settings
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """
    Migrations in offline mode (generate SQL without DB connection)
    Usually not used, but can be useful
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Apply migrations through existing connection"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Main function for async migrations
    Create async engine and apply migrations
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Migrations in online mode (normal mode)
    Connect to DB and apply migrations
    """
    import asyncio
    asyncio.run(run_async_migrations())


# choose mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()