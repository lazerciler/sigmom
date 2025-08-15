#!/usr/bin/env python3
# File: migrations/env.py
"""
Alembic migration environment, configured for SQLAlchemy async app,
modified to use a synchronous engine for autogenerate and migrations.
"""
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context
from app.models import Base
from app.config import Settings

# Alembic config objesi
config = context.config
fileConfig(config.config_file_name)

# -- Model metadata
target_metadata = Base.metadata

# -- Ayarları oku
settings = Settings()

# Async URL'i sync hale getiriyoruz
# e.g. mysql+aiomysql:// → mysql+pymysql://
sync_url = settings.DB_URL.replace("mysql+aiomysql", "mysql+pymysql")


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode using a synchronous engine."""
    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
