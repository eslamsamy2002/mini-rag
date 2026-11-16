import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from schemes import SQLAlchemyBase

from alembic import context

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLAlchemyBase.metadata


def get_db_url() -> str:
    """
    Constructs the database connection string dynamically.
    Priority:
    1. Read environment variables passed into the container
    2. Fall back to defaults matching your Docker network configuration
    """
    user = os.getenv("POSTGRES_USERNAME", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "apprag333")
    host = os.getenv("POSTGRES_HOST", "pgvector")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_MAIN_DATABASE", "ragapp")

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    db_url = get_db_url()
    
    # Override the configuration URL dynamically
    config.set_main_option("sqlalchemy.url", db_url)
    
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = db_url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()