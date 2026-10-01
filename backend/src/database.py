"""Database setup and session handling."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def _engine_kwargs(url: str) -> dict:
    """Driver-specific engine options.

    check_same_thread is a SQLite-only escape hatch and psycopg rejects it, so
    it cannot be passed unconditionally. PostgreSQL instead wants a pool that
    survives an idle connection being cut by the server.
    """
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_recycle": 1800}


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
# Not meant to be called directly: scoping.open_session() / open_system_session()
# wrap it so every session carries the user it is confined to. A bare
# SessionLocal() has no user and refuses to touch an owned table.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
