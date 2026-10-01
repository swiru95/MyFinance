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

# Bumped whenever the terms text (frontend/src/lib/terms.ts) changes in a way
# that needs re-acceptance. Every user with an older (or no) accepted
# version (users.terms_version) is shown the acceptance modal again - see
# routes/settings.py.
TERMS_VERSION = 1

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

    # --- OIDC authentication (OAuth 2.0 access tokens) ----------------------
    # Tokens are validated against any OpenID Connect issuer: the signing keys
    # come from the `jwks_uri` in the issuer's discovery document
    # ({issuer}/.well-known/openid-configuration), and `iss` and `aud` must
    # match what is configured here. Everything else below is an optional extra
    # check that only runs when it is set.
    #
    # Authentication is off only when *nothing* here is set - the same way an
    # unset LLM base URL disables the assessment - so `docker compose up` and
    # local development keep working untouched. A partial configuration is a
    # startup error (see auth.validate_config), not "off": the failure mode of
    # a half-finished deploy would otherwise be an open API.
    auth_issuer: str = ""
    # Accepted `aud`. Comma-separated when more than one. Falls back to the
    # client id (and api://<client id>, which is what Entra v1 tokens carry).
    auth_audience: str = ""
    # The OAuth client id the browser signs in with. Needed by the SPA, and the
    # audience default above; not used to validate tokens beyond that.
    auth_client_id: str = ""

    # --- Entra ID specifics, all optional --------------------------------
    # With only tenant + client id set (how every existing deployment is
    # configured) the issuer is derived from the tenant and the three checks
    # below default to what they always were. With an explicit issuer they
    # default to off. Set any of them to the empty string to switch it off.
    #
    # `tid` must equal this. Guest accounts from another tenant carry a `tid`
    # that is not ours even when the issuer is.
    auth_tenant_id: str = ""
    # Scope that must appear in the token's `scp` (or `scope`) claim. Also what
    # the SPA asks for. Entra-only default "access_as_user": it is the
    # discriminator between an access token for this API and an ID token.
    auth_api_scope: str | None = None
    # App role that must appear in `roles`. Combined with "Assignment required"
    # on the enterprise application this is the actual gate. Entra-only
    # default "MyFinance.User".
    auth_required_role: str | None = None

    # Require the JWT header `typ` to be "at+jwt" (RFC 9068, "JWT Profile for
    # OAuth 2.0 Access Tokens"). One of this or a scope (above) is mandatory:
    # `iss`, `aud` and the signature are identical on the ID token the browser
    # gets at sign-in and the access token it should send, so without one of
    # these two checks a generic issuer's ID token is accepted as an API
    # credential. Set this for issuers that mint RFC 9068 access tokens
    # (Keycloak does not by default - its access tokens carry typ "Bearer" - so
    # use a scope there; Entra's carry typ "JWT" and use the scope too). Entra
    # needs neither: tenant + client id imply the access_as_user scope.
    auth_require_at_jwt_typ: bool = False

    # Signing keys and the discovery document are cached for this long. Issuers
    # rotate keys, so this cannot be indefinite; an unknown key id forces an
    # earlier refresh (at most once per auth_jwks_min_refresh_seconds).
    auth_jwks_cache_seconds: int = 3600
    auth_jwks_min_refresh_seconds: int = 30
    # Clock skew tolerated on exp/nbf.
    auth_leeway_seconds: int = 60

    # --- User identity ---------------------------------------------------
    # Secret mixed into the subject hash: users.subject_hash =
    # HMAC-SHA256(pepper, issuer + "|" + sub). The database therefore holds no
    # identifier that can be tied back to a person without this value. Required
    # when authentication is on; losing or changing it orphans every user's
    # data, so it belongs in the same secret store as the database credentials.
    subject_pepper: str = ""
    # Whose existing (pre multi-user) data the schema job assigns to. `sub` is
    # the token's own claim and `iss` defaults to the configured issuer. Only
    # read by `python -m src.schema`, and only when it finds rows with no owner.
    bootstrap_iss: str = ""
    bootstrap_sub: str = ""

    # --- Database ---------------------------------------------------------
    # On PostgreSQL the application must connect as a role that is subject to
    # row-level security (src/rls.py): not a superuser, no BYPASSRLS, not the
    # owner of the tables. Startup refuses to proceed otherwise, because every
    # query would work and none would be protected. Switch off only for a
    # deliberate one-off, e.g. running the application as the owner locally.
    rls_role_check: bool = True

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
