"""Settings endpoints (base currency)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.settings import Setting
from ..schemas.settings import SettingsIn
from ..config import BASE_CURRENCIES, DEFAULT_TIMEZONE, TIMEZONES
from .helpers import get_timezone

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _payload(db: Session) -> dict:
    s = db.query(Setting).filter(Setting.key == "base_currency").first()
    return {
        "base_currency": s.value if s else "PLN",
        "allowed_currencies": BASE_CURRENCIES,
        "timezone": get_timezone(db),
        "allowed_timezones": TIMEZONES,
        "default_timezone": DEFAULT_TIMEZONE,
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
    db.commit()
    return _payload(db)
