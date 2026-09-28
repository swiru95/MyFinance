"""Settings endpoints (base currency, timezone, advanced-feature switches,
terms-of-use acceptance)."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.settings import Setting
from ..schemas.settings import SettingsIn, TermsAcceptIn
from ..config import BASE_CURRENCIES, DEFAULT_TIMEZONE, TERMS_VERSION, TIMEZONES
from .helpers import get_features, get_timezone

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _terms_state(db: Session) -> dict:
    s = db.query(Setting).filter(Setting.key == "terms_accepted").first()
    accepted_version = None
    accepted_at = None
    if s and s.value:
        data = json.loads(s.value)
        accepted_version = data.get("version")
        accepted_at = data.get("accepted_at")
    return {
        "current_version": TERMS_VERSION,
        "accepted_version": accepted_version,
        "accepted_at": accepted_at,
    }


def _payload(db: Session) -> dict:
    s = db.query(Setting).filter(Setting.key == "base_currency").first()
    return {
        "base_currency": s.value if s else "PLN",
        "allowed_currencies": BASE_CURRENCIES,
        "timezone": get_timezone(db),
        "allowed_timezones": TIMEZONES,
        "default_timezone": DEFAULT_TIMEZONE,
        # Always resolved (never missing) - schema.py seeds a default on every
        # startup, and get_features falls back to all-false besides.
        "features": get_features(db).model_dump(),
        "terms": _terms_state(db),
    }


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return _payload(db)


def _put(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


@router.put("")
def update_settings(payload: SettingsIn, db: Session = Depends(get_db)):
    _put(db, "base_currency", payload.base_currency)
    if payload.timezone is not None:
        _put(db, "timezone", payload.timezone)
    if payload.features is not None:
        # FeatureFlags' own validator has already forced fire off if
        # portfolio is off, so what lands here is always consistent.
        _put(db, "features", payload.features.model_dump_json())
    db.commit()
    return _payload(db)


@router.post("/terms/accept")
def accept_terms(payload: TermsAcceptIn, db: Session = Depends(get_db)):
    if payload.version != TERMS_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"terms version {payload.version} is not current ({TERMS_VERSION})",
        )
    value = json.dumps({
        "version": payload.version,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    })
    _put(db, "terms_accepted", value)
    db.commit()
    return _payload(db)
