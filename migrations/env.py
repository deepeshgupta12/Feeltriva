"""Alembic environment. Migrations are hand-written SQL reviewed against specs/schema.sql.

Connects with MIGRATION_DATABASE_URL (schema owner); falls back to DATABASE_URL.
"""

import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("Set MIGRATION_DATABASE_URL (or DATABASE_URL) to run migrations")

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
