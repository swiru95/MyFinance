"""Request and response shapes for /api/contacts. No response ever carries an address."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ContactState(BaseModel):
    opted_in: bool
    # Opting in is possible: the sign-in's token has a verified e-mail address
    # and the server has a contact key to store it under.
    can_opt_in: bool


class UnsubscribeIn(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)
