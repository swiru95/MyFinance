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


# Wallet assessment styles offered in the UI. The key is stored on the report
# row and drives the prompt; the wording the user reads is translated in the
# frontend, so nothing here is user-facing.
REPORT_STYLES = ["safe", "balanced", "risky", "long_term"]
REPORT_LANGUAGES = ["en", "pl"]


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{DATA_DIR / 'myfinance.db'}"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # --- Entra ID SSO (OAuth 2.0 authorization code + PKCE) -----------------
    # Unset tenant or client id disables authentication entirely, the same way
    # an unset LLM base URL disables the assessment. That keeps `docker compose
    # up` and local development working untouched; the Helm chart always sets
    # both. main.py logs a loud warning on startup when it is off, because the
    # failure mode of a misconfigured deploy is an open API.
    auth_tenant_id: str = ""
    auth_client_id: str = ""
    # The scope the SPA asks for. The app registration exposes it on its own
    # Application ID URI, so one registration serves as both the client and the
    # protected API - see README "Entra ID SSO".
    auth_api_scope: str = "access_as_user"
    # App role a caller must hold. Combined with "Assignment required" on the
    # enterprise application this is the actual gate: a valid tenant token
    # without the role is rejected. Empty means any authenticated tenant user,
    # which for a single-person finance app is not what you want.
    auth_required_role: str = "MyFinance.User"
    # Signing keys are cached for this long. Microsoft rotates them, so this
    # cannot be indefinite; an hour is well inside the rotation window and
    # keeps login off the critical path of every request.
    auth_jwks_cache_seconds: int = 3600
    # Clock skew tolerated on exp/nbf.
    auth_leeway_seconds: int = 60

    # --- Wallet assessment (llama-server, OpenAI-compatible API) -------------
    # Unset base URL or key disables the feature rather than failing requests:
    # the Report page says so instead of erroring on every generation.
    llm_base_url: str = ""
    llm_api_key: str = ""
    # Writes the assessment. A reasoning model, so replies carry a separate
    # reasoning_content field that is deliberately not stored or shown.
    llm_model: str = "Thinker"
    # Translates the finished English report into Polish. A Polish-native model
    # beats asking the author model to write Polish directly.
    llm_translate_model: str = "Bielik"
    # The server presents a certificate from the lab's own CA, which is not in
    # the image's trust store. Point this at a PEM bundle holding that CA and
    # verification turns on properly.
    #
    # The bundle must contain the *intermediate* as well as the root. The root
    # carries no keyUsage extension, and Python 3.13 enables VERIFY_X509_STRICT
    # by default, which rejects a CA cert without one ("CA cert does not include
    # key usage extension"). With the intermediate present it becomes the trust
    # anchor and the root is never examined, so strict verification passes
    # without being weakened. This is why the other consumers of this server
    # ended up on verify=off; they do not need to be.
    llm_ca_bundle: str = ""
    # Only consulted when no CA bundle is given. Off by default so a missing
    # bundle degrades to "works, unverified" rather than "cannot connect".
    llm_verify_tls: bool = False

    # --- Mutual TLS -----------------------------------------------------
    # The pod already holds an autocert-issued identity for talking to
    # PostgreSQL, and that certificate carries clientAuth in its EKU, so the
    # same pair authenticates it to llama-server. Where this is set the pod
    # proves who it is with a certificate instead of a shared bearer token.
    #
    # Harmless before the server asks for one: a server that does not request
    # a client certificate simply never sees it.
    llm_client_cert: str = ""
    llm_client_key: str = ""
    # Set when the key is protected; autocert's is not, so normally empty.
    llm_client_key_password: str = ""
    # Generous: the router loads one model at a time, so a request can be
    # waiting on a 76 GB model being paged in before a token is produced.
    llm_timeout: float = 900.0
    # Output budget for the assessment. This has to cover the model's reasoning
    # as well as the report, because a reasoning model spends the same budget on
    # both - at 4096 it reasons to the limit and answers with empty content.
    llm_max_tokens: int = 16384
    # Translation needs no reasoning, only headroom over the English text, which
    # Polish runs longer than.
    llm_translate_max_tokens: int = 8192

    class Config:
        env_prefix = "MYFINANCE_"


settings = Settings()
