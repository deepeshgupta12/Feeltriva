"""Alembic environment. Migrations are hand-written SQL reviewed against specs/schema.sql.

Connects with MIGRATION_DATABASE_URL (schema owner), falling back to DATABASE_URL; both are
read from the environment first and then from `.env`.
"""

import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    # Same source as the application: values from `.env` in the working directory.
    from feeltriva_api.settings import Settings

    _settings = Settings()
    url = _settings.migration_database_url or _settings.database_url
if not url:
    raise SystemExit("Set MIGRATION_DATABASE_URL (or DATABASE_URL), in the environment or .env, to run migrations")

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
