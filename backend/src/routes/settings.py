"""Settings endpoints (base currency, timezone, advanced-feature switches,
terms-of-use acceptance).

Settings are per user. Terms acceptance is not a setting any more: it lives on
the user row (models/user.py), which is not one of the scoped tables, so it is
looked up by the caller's id explicitly.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import Principal, require_user
from ..deps import get_db
from ..models.user import User
from ..models.settings import Setting
from ..schemas.settings import BirthYearIn, SettingsIn, TermsAcceptIn
from ..config import BASE_CURRENCIES, DEFAULT_TIMEZONE, TERMS_VERSION, TIMEZONES
from .helpers import get_features, get_timezone

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _terms_state(db: Session, user_id) -> dict:
    user = db.get(User, user_id)
    accepted_at = user.terms_accepted_at if user else None
    return {
        "current_version": TERMS_VERSION,
        "accepted_version": user.terms_version if user else None,
        # Stored naive-but-UTC; sent as an explicit UTC instant.
        "accepted_at": accepted_at.replace(tzinfo=timezone.utc).isoformat() if accepted_at else None,
    }


def _birth_year(db: Session, user_id) -> int | None:
    user = db.get(User, user_id)
    return user.birth_year if user else None


def _payload(db: Session, user_id) -> dict:
    s = db.query(Setting).filter(Setting.key == "base_currency").first()
    return {
        "base_currency": s.value if s else "PLN",
        "allowed_currencies": BASE_CURRENCIES,
        "timezone": get_timezone(db),
        "allowed_timezones": TIMEZONES,
        "default_timezone": DEFAULT_TIMEZONE,
        # Always resolved (never missing): a user who has never saved a choice
        # has no row, and get_features turns that into "everything off".
        "features": get_features(db).model_dump(),
        "terms": _terms_state(db, user_id),
        # Optional; encrypted at rest under the user's own key (models/user.py).
        "birth_year": _birth_year(db, user_id),
    }


@router.get("")
def get_settings(db: Session = Depends(get_db), principal: Principal = Depends(require_user)):
    return _payload(db, principal.user_id)


def _put(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


@router.put("")
def update_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    _put(db, "base_currency", payload.base_currency)
    if payload.timezone is not None:
        _put(db, "timezone", payload.timezone)
    if payload.features is not None:
        # FeatureFlags' own validator has already forced fire off if
        # portfolio is off, so what lands here is always consistent.
        _put(db, "features", payload.features.model_dump_json())
    db.commit()
    return _payload(db, principal.user_id)


@router.post("/terms/accept")
def accept_terms(
    payload: TermsAcceptIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    if payload.version != TERMS_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"terms version {payload.version} is not current ({TERMS_VERSION})",
        )
    user = db.get(User, principal.user_id)
    user.terms_version = payload.version
    # Naive UTC, like every other timestamp column here.
    user.terms_accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return _payload(db, principal.user_id)


@router.put("/birth-year")
def set_birth_year(
    payload: BirthYearIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """Set (or clear, with null) the optional birth year."""
    user = db.get(User, principal.user_id)
    user.birth_year = payload.birth_year
    db.commit()
    return _payload(db, principal.user_id)
