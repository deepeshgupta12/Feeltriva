from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Database:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite"):
            # In-memory SQLite is for unit tests only.
            self.engine: Engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        else:
            self.engine = create_engine(url, pool_pre_ping=True)
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    @property
    def is_postgres(self) -> bool:
        return self.engine.dialect.name == "postgresql"

    @contextmanager
    def transaction(self, owner_subject: str | None, *, role: str = "user") -> Iterator[Session]:
        """One transaction scoped to a caller. In PostgreSQL the subject is bound to the
        transaction so row-level security policies apply even if a query forgets its filter."""
        with self._factory() as session, session.begin():
            if self.is_postgres:
                session.execute(
                    text("SELECT set_config('app.owner_subject', :s, true), set_config('app.role', :r, true)"),
                    {"s": owner_subject or "", "r": role},
                )
            yield session

    def ping(self) -> bool:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
