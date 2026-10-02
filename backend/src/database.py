"""Database setup and session handling."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.sql import Select

from .config import settings
from .crypto.core import KeyRing, activated

# Where a session keeps its user's key ring (a crypto.core.KeyRing), next to the
# user id scoping.py keeps in `info`. Absent on a session that holds no key.
KEYRING_KEY = "keyring"


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


class KeyedSession(Session):
    """A session that decrypts and encrypts with *its own user's* key, and only
    while it is itself doing the work.

    The encrypted column types (crypto/fields.py) take their key from the ring
    `crypto.core.activated` puts in force. This session does that around every
    statement it executes and every flush, with the ring held in its own `info`;
    so the ring in force is always the one belonging to the session that is
    running, never a leftover from another request, thread or user, and outside
    those moments nothing can decrypt.

    SELECTs are executed with `prebuffer_rows`: the ORM then builds every row
    inside `execute()` - under the key - instead of lazily while the caller
    iterates, long after the key has been put away. (`Query.all()` loaded
    everything anyway; this only moves *when* for the rest.)
    """

    @contextmanager
    def _unlocked(self):
        ring = self.info.get(KEYRING_KEY)
        if ring is None:
            yield
            return
        if not isinstance(ring, KeyRing):  # pragma: no cover - programming error
            raise TypeError("session.info['keyring'] must be a KeyRing")
        with activated(ring):
            yield

    def _execute_internal(self, statement, *args, **kw):
        with self._unlocked():
            if isinstance(statement, Select):
                options = dict(kw.get("execution_options") or {})
                options["prebuffer_rows"] = True
                kw["execution_options"] = options
            return super()._execute_internal(statement, *args, **kw)

    def flush(self, objects=None):
        with self._unlocked():
            return super().flush(objects)


# Not meant to be called directly: scoping.open_session() / open_system_session()
# wrap it so every session carries the user it is confined to (and that user's
# key). A bare SessionLocal() has no user and refuses to touch an owned table.
SessionLocal = sessionmaker(class_=KeyedSession, autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
