"""FastAPI dependencies shared by every router."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from .auth import Principal, require_user
from .scoping import open_session


def get_db(principal: Principal = Depends(require_user)) -> Iterator[Session]:
    """A session confined to the calling user's rows (see scoping.py).

    Depending on `require_user` is what makes this safe: there is no way to get
    a session from here without a validated user, and none that is not scoped
    to that user. The session carries that user's key ring (unwrapped from the
    live token for this request), which is what lets the encrypted columns
    read and write transparently - and nothing else can.
    """
    db = open_session(principal.user_id, principal.keyring)
    try:
        yield db
    finally:
        db.close()
