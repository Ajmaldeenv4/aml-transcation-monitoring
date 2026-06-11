"""Database engine and session management.

Defaults to a local SQLite file. Set ``SENTINEL_DB_URL`` (e.g. a Postgres URL) to
swap the backend without code changes — satisfying the "SQLite first, Postgres
optional" requirement.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from sentinel.config import REPO_ROOT

DEFAULT_DB_URL = f"sqlite:///{(REPO_ROOT / 'sentinel.db').as_posix()}"
DB_URL = os.environ.get("SENTINEL_DB_URL", DEFAULT_DB_URL)

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Create all tables. Import models first so they register with SQLModel."""
    import sentinel.casestore.tables  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
