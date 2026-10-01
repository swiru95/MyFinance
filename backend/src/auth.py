"""OIDC access-token validation and the per-request user.

The browser signs in against an OpenID Connect provider and sends the resulting
*access* token here as a bearer credential. This module is the other half: it
checks that the token really was issued by the configured issuer, for this API,
and then maps it to a user row (creating it on first sight).

What is checked, always: signature (against the keys the issuer publishes at
the `jwks_uri` of its discovery document), `iss`, `aud`, `exp`, and that `sub`
is present. What is checked only when configured: the Entra `tid`, a required
scope in `scp`/`scope`, and a required app role in `roles`. A deployment with
nothing but a tenant id and client id gets the Entra defaults for all three, so
configuration written for the Entra-only version keeps meaning what it meant.

What this module deliberately never does is keep or log the identity claims.
`sub` is hashed (identity.subject_hash) and dropped; `name`, `email`,
`preferred_username` and `oid` are not read.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import identity
from .config import settings
from .services.users import get_or_create_local_user, get_or_create_user

log = logging.getLogger(__name__)

# Asymmetric only. Never "none", never HS*: with a public JWKS an HMAC
# algorithm would let anyone who can read the key forge tokens.
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]

_ENTRA_DEFAULT_SCOPE = "access_as_user"
_ENTRA_DEFAULT_ROLE = "MyFinance.User"


class AuthConfigError(RuntimeError):
    """Authentication is configured inconsistently. Raised at startup."""


# --- Configuration, resolved --------------------------------------------


def _entra_v2_issuer(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/v2.0"


def _entra_compat() -> bool:
    """Only a tenant (and client id) is set: the pre-OIDC Entra configuration."""
    return not settings.auth_issuer and bool(settings.auth_tenant_id)


def issuer() -> str:
    """The canonical issuer. This exact string, not the token's own `iss`, goes
    into the subject hash, so that two token versions an issuer may emit for
    one person (Entra v1 and v2) still resolve to the same user."""
    if settings.auth_issuer:
        return settings.auth_issuer
    if settings.auth_tenant_id:
        return _entra_v2_issuer(settings.auth_tenant_id)
    return ""


def audiences() -> list[str]:
    if settings.auth_audience:
        return [a.strip() for a in settings.auth_audience.split(",") if a.strip()]
    cid = settings.auth_client_id
    # Entra issues `aud` as the bare client id for v2 tokens and as the
    # Application ID URI for v1 ones, and which you get follows from the token
    # version the app registration is set to emit.
    return [cid, f"api://{cid}"] if cid else []


def _accepted_issuers() -> set[str]:
    accepted = {issuer()}
    tid = settings.auth_tenant_id
    if tid and issuer() == _entra_v2_issuer(tid):
        # A new app registration ships with `requestedAccessTokenVersion: null`,
        # i.e. v1, and a v1 token comes from sts.windows.net rather than the v2
        # endpoint the sign-in went through. Accepting both means the API
        # works whether or not that manifest field was set to 2, instead of
        # rejecting every token with an issuer mismatch that looks nothing like
        # a configuration problem.
        accepted.add(f"https://sts.windows.net/{tid}/")
    return accepted


def required_scope() -> str:
    if settings.auth_api_scope is not None:
        return settings.auth_api_scope
    return _ENTRA_DEFAULT_SCOPE if _entra_compat() else ""


def required_role() -> str:
    if settings.auth_required_role is not None:
        return settings.auth_required_role
    return _ENTRA_DEFAULT_ROLE if _entra_compat() else ""


def requires_access_token_proof() -> bool:
    """Whether this deployment can tell an access token from an ID token.

    The two carry the same issuer, audience and signature, so the API needs
    something that sets them apart: a scope that only access tokens carry, or
    the RFC 9068 `typ` header. Entra configured by tenant and client id has the
    scope by default; anything else has to choose.
    """
    return bool(required_scope()) or settings.auth_require_at_jwt_typ


def auth_enabled() -> bool:
    """Authentication is on when an issuer and an audience are both known."""
    return bool(issuer() and audiences())


def scope_uri() -> str:
    """The scope string the SPA requests."""
    scope = required_scope()
    if scope and settings.auth_client_id and _entra_compat():
        return f"api://{settings.auth_client_id}/{scope}"
    return scope


def _is_local(url: str) -> bool:
    return (urlsplit(url).hostname or "") in ("localhost", "127.0.0.1", "::1")


def validate_config() -> None:
    """Refuse to start on a configuration that would be unsafe or useless.

    Called once at startup (main.lifespan). Nothing set at all is fine - that
    is the documented way to run locally. Something set but not enough to
    validate tokens is not: it would mean serving every user's data to anyone.
    """
    touched = [
        name
        for name, value in (
            ("MYFINANCE_AUTH_ISSUER", settings.auth_issuer),
            ("MYFINANCE_AUTH_AUDIENCE", settings.auth_audience),
            ("MYFINANCE_AUTH_CLIENT_ID", settings.auth_client_id),
            ("MYFINANCE_AUTH_TENANT_ID", settings.auth_tenant_id),
        )
        if value
    ]
    if not touched:
        return
    if not auth_enabled():
        raise AuthConfigError(
            f"authentication is partly configured ({', '.join(touched)}) but needs an issuer "
            "(MYFINANCE_AUTH_ISSUER, or MYFINANCE_AUTH_TENANT_ID for Entra) and an audience "
            "(MYFINANCE_AUTH_AUDIENCE, or MYFINANCE_AUTH_CLIENT_ID)"
        )
    if not settings.subject_pepper:
        raise AuthConfigError(
            "MYFINANCE_SUBJECT_PEPPER is required when authentication is enabled"
        )
    if urlsplit(issuer()).scheme != "https" and not _is_local(issuer()):
        raise AuthConfigError("the OIDC issuer must be an https URL")
    if not requires_access_token_proof():
        raise AuthConfigError(
            "nothing distinguishes an access token from an ID token: with this issuer, an ID "
            "token for the right audience would be accepted as an API credential. Set "
            "MYFINANCE_AUTH_API_SCOPE (a scope that only access tokens carry) or "
            "MYFINANCE_AUTH_REQUIRE_AT_JWT_TYP=true (RFC 9068 `typ: at+jwt`)"
        )


# --- Keys ---------------------------------------------------------------


def _fetch_json(url: str) -> dict:
    """GET a JSON document. The one place this module touches the network, so
    tests replace it rather than patching an HTTP library."""
    resp = httpx.get(url, timeout=10.0, follow_redirects=False)
    resp.raise_for_status()
    return resp.json()


class KeyUnavailable(RuntimeError):
    """The issuer's keys could not be fetched (as opposed to: not found)."""


class _KeyStore:
    """Discovery document and JWKS, cached.

    Both are re-fetched after `auth_jwks_cache_seconds`, and the JWKS earlier
    when a token names a key id we do not hold - that is what a key rotation
    looks like from here. That early refetch is rate-limited so a stream of
    tokens with made-up key ids cannot turn this service into a way of hammering
    the identity provider.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jwks_uri: str | None = None
        self._discovered_at = 0.0
        self._keys: dict[str | None, object] = {}
        self._keys_at = 0.0

    def _discover(self, now: float) -> str:
        if self._jwks_uri and now - self._discovered_at < settings.auth_jwks_cache_seconds:
            return self._jwks_uri
        url = issuer().rstrip("/") + "/.well-known/openid-configuration"
        try:
            doc = _fetch_json(url)
        except (httpx.HTTPError, ValueError) as exc:
            raise KeyUnavailable(f"discovery document unreachable: {exc}") from exc
        # OIDC Discovery 4.3: the document must name the issuer it was fetched
        # for, which stops a redirect or a mis-pointed config from quietly
        # substituting someone else's key set.
        if doc.get("issuer") != issuer():
            raise KeyUnavailable("discovery document is for a different issuer")
        jwks_uri = doc.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not (
            urlsplit(jwks_uri).scheme == "https" or _is_local(jwks_uri)
        ):
            raise KeyUnavailable("discovery document has no usable jwks_uri")
        self._jwks_uri, self._discovered_at = jwks_uri, now
        return jwks_uri

    def _refresh(self, now: float) -> None:
        jwks_uri = self._discover(now)
        try:
            jwk_set = jwt.PyJWKSet.from_dict(_fetch_json(jwks_uri))
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            raise KeyUnavailable(f"signing keys unavailable: {exc}") from exc
        self._keys = {k.key_id: k.key for k in jwk_set.keys}
        self._keys_at = now

    def signing_key(self, kid: str | None):
        now = time.monotonic()
        with self._lock:
            stale = now - self._keys_at >= settings.auth_jwks_cache_seconds
            if stale or not self._keys:
                self._refresh(now)
            elif (
                kid not in self._keys
                and now - self._keys_at >= settings.auth_jwks_min_refresh_seconds
            ):
                self._refresh(now)
            if kid in self._keys:
                return self._keys[kid]
            # A token with no `kid` is only unambiguous against a one-key set.
            if kid is None and len(self._keys) == 1:
                return next(iter(self._keys.values()))
            return None

    def reset(self) -> None:
        with self._lock:
            self._jwks_uri, self._discovered_at = None, 0.0
            self._keys, self._keys_at = {}, 0.0


_store = _KeyStore()


def reset_key_cache() -> None:
    _store.reset()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# auto_error=False so a missing header reaches our own handler and produces a
# 401 carrying WWW-Authenticate, rather than FastAPI's bare 403.
_bearer = HTTPBearer(auto_error=False)


def _claim_list(value) -> list[str]:
    """`scp`/`scope` is a space-separated string; `roles` is a list. Accept both
    shapes for both, because providers differ."""
    if isinstance(value, str):
        return value.split()
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return []


def verify_token(token: str) -> dict:
    """Return the validated claims, or raise.

    Signature, issuer, audience and expiry are all checked. Nothing here trusts
    a claim before the signature has been verified against the issuer's keys.
    """
    if not requires_access_token_proof():
        # validate_config() stops the application starting like this; this is
        # the same refusal for anything that reaches here without it (a test, a
        # settings change at runtime). Failing open would accept ID tokens.
        log.error("authentication is enabled with no scope and no typ requirement; refusing tokens")
        raise HTTPException(500, "Server authentication configuration is incomplete")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token") from exc

    kid = header.get("kid")
    if kid is not None and not isinstance(kid, str):
        raise _unauthorized("Invalid token")
    try:
        key = _store.signing_key(kid)
    except KeyUnavailable as exc:
        # Reaching the identity provider failed. That is this service being
        # unable to answer, not the caller being unauthenticated, and a 503
        # says so where a 401 would send them round the login loop.
        log.warning("Could not resolve the issuer's signing key: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot reach the identity provider's signing keys",
        ) from exc
    if key is None:
        raise _unauthorized("Token was signed by an unknown key")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=audiences(),
            leeway=settings.auth_leeway_seconds,
            # Checked below against a set, which older PyJWT cannot express here.
            options={"verify_iss": False, "require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise _unauthorized("Token was not issued for this application") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"Invalid token: {exc}") from exc

    if claims.get("iss") not in _accepted_issuers():
        raise _unauthorized("Token was not issued by the configured issuer")

    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise _unauthorized("Token has no subject")

    # Entra only: guest accounts from another tenant carry a `tid` that is not
    # ours even when the issuer is, so this is a separate check rather than a
    # corollary.
    if settings.auth_tenant_id and claims.get("tid") != settings.auth_tenant_id:
        raise _unauthorized("Token was not issued by the configured tenant")

    # RFC 9068 section 2.1: an access token's header says so. Read from the
    # header only after the signature has verified, so it is the issuer's word.
    # `application/at+jwt` is the same media type spelled out (RFC 7515 4.1.9).
    if settings.auth_require_at_jwt_typ:
        typ = header.get("typ")
        if not isinstance(typ, str) or typ.lower() not in ("at+jwt", "application/at+jwt"):
            raise _unauthorized(
                "Token is not an access token for this API "
                '(its header typ is not "at+jwt"); an ID token will not do'
            )

    # With a scope configured, this must be an *access token minted for this
    # API*, not merely a token carrying the right audience. An ID token from
    # the same registration has the same `aud`, `iss` and `tid`, and carries
    # `roles` too when the user is assigned one - so every other check would
    # pass and a sign-in token would work as an API credential. Entra sets
    # `scp` on delegated access tokens and never on ID tokens.
    scope = required_scope()
    if scope and scope not in _claim_list(claims.get("scp")) + _claim_list(claims.get("scope")):
        raise _unauthorized(
            "Token is not an access token for this API "
            f"(no {scope} scope); an ID token will not do"
        )

    role = required_role()
    if role and role not in _claim_list(claims.get("roles")):
        # 403, not 401: they proved who they are and the answer is still no, so
        # sending them back through login would achieve nothing.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is not assigned the {role} role for this application",
        )

    return claims


class Principal:
    """Who is making the request: this application's own id for them, and
    nothing else. The token's claims are not kept, so there is no name, email
    or subject on this object to end up in a log line or a response."""

    __slots__ = ("user_id",)

    def __init__(self, user_id: uuid.UUID):
        self.user_id = user_id

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<Principal {self.user_id}>"


def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Router-level dependency guarding every data endpoint.

    Also what every database session is scoped by (deps.get_db), so a route
    cannot be reached, or reach the database, without passing through here.
    """
    if not auth_enabled():
        return Principal(get_or_create_local_user())
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Not authenticated")
    claims = verify_token(credentials.credentials)
    try:
        digest = identity.subject_hash(issuer(), claims["sub"])
    except identity.PepperMissing as exc:
        log.error("%s", exc)
        raise HTTPException(500, "Server identity configuration is incomplete") from exc
    principal = Principal(get_or_create_user(digest))
    # Handy for anything downstream that wants the caller without re-declaring
    # the dependency (exception handlers, logging middleware).
    request.state.principal = principal
    return principal
