"""Notification e-mail: opt in, opt out, unsubscribe by link. Nothing is sent yet.

This is the one place a user's e-mail address is ever stored, and only because
they asked: `POST /opt-in` reads `email` from the access token the request was
signed with, and only when the identity provider also says `email_verified` -
the browser never sends an address, so there is none to typo or forge. It is
sealed under the contact key (crypto/contacts.py), which is a separate secret
from the one that protects financial data. Opting out, or following an
unsubscribe link, erases the address.

The unsubscribe endpoint is not authenticated, by necessity: the person clicking
a link in an e-mail is not signed in. The link's token is an HMAC the sender can
recompute from the contact key; the database holds only its hash.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import LargeBinary, bindparam, text, update
from sqlalchemy.orm import Session

from .. import rls
from ..auth import Principal, require_user
from ..crypto import contacts as contact_crypto
from ..database import engine
from ..deps import get_db
from ..models.contact import UserContact
from ..schemas.contacts import ContactState, UnsubscribeIn
from ..scoping import open_system_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["contacts"])
# Registered without the router-level authentication every other router gets.
public = APIRouter(prefix="/api/contacts", tags=["contacts"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


def _state(db: Session, principal: Principal) -> ContactState:
    row = db.get(UserContact, principal.user_id)
    return ContactState(
        opted_in=bool(row and row.notify_opt_in),
        # Whether opting in is possible right now: the token carries an address
        # the provider vouches for, and this deployment has a contact key.
        can_opt_in=principal.verified_email() is not None and contact_crypto.configured(),
    )


@router.get("", response_model=ContactState)
def get_contact(db: Session = Depends(get_db), principal: Principal = Depends(require_user)):
    return _state(db, principal)


@router.post("/opt-in", response_model=ContactState)
def opt_in(db: Session = Depends(get_db), principal: Principal = Depends(require_user)):
    email = principal.verified_email()
    if email is None:
        raise HTTPException(
            status_code=409,
            detail="Your sign-in did not provide a verified e-mail address, so there is nothing to subscribe.",
        )
    email = email.strip()
    if len(email) > 254 or not _EMAIL.match(email):
        raise HTTPException(status_code=409, detail="The e-mail address in your sign-in is not usable.")
    try:
        sealed_email = contact_crypto.seal_email(principal.user_id, email)
    except contact_crypto.ContactKeyError as exc:
        log.error("%s", exc)
        raise HTTPException(status_code=503, detail="Notifications are not configured on this server.") from exc

    row = db.get(UserContact, principal.user_id)
    if row is None:
        row = UserContact(user_id=principal.user_id, token_version=1)
        db.add(row)
    elif not row.notify_opt_in and row.unsubscribe_token_hash is not None:
        # Opting in again after opting out: the old token, which may be in mail
        # already sent, must not unsubscribe the new subscription.
        row.token_version += 1
    row.email = sealed_email
    row.email_verified = True
    row.notify_opt_in = True
    row.unsubscribe_token_hash = contact_crypto.token_hash(
        contact_crypto.unsubscribe_token(principal.user_id, row.token_version)
    )
    db.commit()
    log.info("user %s opted in to notifications", principal.user_id)
    return _state(db, principal)


@router.post("/opt-out", response_model=ContactState)
def opt_out(db: Session = Depends(get_db), principal: Principal = Depends(require_user)):
    row = db.get(UserContact, principal.user_id)
    if row is not None:
        row.notify_opt_in = False
        row.email = None  # the address is erased, not just switched off
        db.commit()
        log.info("user %s opted out of notifications", principal.user_id)
    return _state(db, principal)


@public.post("/unsubscribe")
def unsubscribe(payload: UnsubscribeIn, request: Request):
    """Unsubscribe by the token in an e-mail's link. Idempotent. 404 for a token
    that matches nothing (a link from before the person opted in again, or forged)."""
    digest = contact_crypto.token_hash(payload.token)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            changed = conn.execute(
                text(f"SELECT public.{rls.CONTACT_UNSUBSCRIBE}(:h)").bindparams(
                    bindparam("h", type_=LargeBinary)
                ),
                {"h": digest},
            ).scalar_one()
    else:
        db = open_system_session()
        try:
            changed = db.execute(
                update(UserContact)
                .where(UserContact.unsubscribe_token_hash == digest)
                .values(notify_opt_in=False, email=None)
            ).rowcount
            db.commit()
        finally:
            db.close()
    if not changed:
        raise HTTPException(status_code=404, detail="This unsubscribe link is not valid.")
    return {"unsubscribed": True}
