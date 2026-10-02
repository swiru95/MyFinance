"""Request and response shapes for /api/recovery."""
from __future__ import annotations

from pydantic import BaseModel, Field


class StatusOut(BaseModel):
    # True when this sign-in cannot unlock the account's data: only the recovery
    # code can restore access.
    locked: bool
    configured: bool
    confirmed: bool
    created_at: str | None = None


class CreateIn(BaseModel):
    # A confirmed code is not silently replaced; the client must say so.
    replace: bool = False


class CreatedOut(BaseModel):
    code: str


class CodeIn(BaseModel):
    # Generous: separators and case are ignored when the code is read.
    code: str = Field(..., min_length=1, max_length=128)


class RestoreOut(BaseModel):
    restored: bool
    # "recovered": the old data now answers to this sign-in; "rewrapped": the
    # account was the same one and only its key wrapping changed.
    result: str
