"""Application configuration."""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

# /app/data exists inside Docker; outside, fall back to a local ./data dir.
_DEFAULT_DATA = "/app/data" if Path("/app").exists() else str(Path(__file__).resolve().parent.parent / "data")
DATA_DIR = Path(os.environ.get("MYFINANCE_DATA_DIR", _DEFAULT_DATA))
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    DATA_DIR = Path.cwd() / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_CURRENCIES = ["PLN", "EUR", "USD", "CHF"]

# Offered in Settings. A curated list beats the full IANA database here - it is
# a dropdown a person reads, not a machine lookup.
TIMEZONES = [
    "Europe/Warsaw",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Zurich",
    "Europe/Paris",
    "Europe/Madrid",
    "Europe/Kyiv",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Asia/Tokyo",
    "Asia/Dubai",
    "Australia/Sydney",
    "UTC",
]
DEFAULT_TIMEZONE = "Europe/Warsaw"


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{DATA_DIR / 'myfinance.db'}"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_prefix = "MYFINANCE_"


settings = Settings()
