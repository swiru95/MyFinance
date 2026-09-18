"""Entra ID access-token validation.

The browser runs the OAuth 2.0 authorization code flow with PKCE against
Entra and sends the resulting *access* token here as a bearer credential. This
module is the other half: it checks that the token really was issued by the
configured tenant, for this API, to someone holding the required app role.

One app registration plays both parts. It carries an SPA redirect URI and it
exposes a scope on its own Application ID URI, so the client id below is both
the `client_id` the browser authenticates with and the `aud` the token is
issued for.
"""
from __future__ import annotations

import logging
import threading

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

log = logging.getLogger(__name__)

ALGORITHMS = ["RS256"]


def auth_enabled() -> bool:
    """Authentication is on only when both halves of the identity are set.

    A half-configured deploy is a misconfiguration, not a mode: without the
    tenant there is nothing to fetch keys from, and without the client id there
    is no audience to check against.
    """
    return bool(settings.auth_tenant_id and settings.auth_client_id)


def _authority() -> str:
    return f"https://login.microsoftonline.com/{settings.auth_tenant_id}"


def scope_uri() -> str:
    return f"api://{settings.auth_client_id}/{settings.auth_api_scope}"


def _valid_issuers() -> set[str]:
    """Both token versions, because the manifest decides which one you get.

    A new app registration ships with `requestedAccessTokenVersion: null`,
    which means v1 - and a v1 access token is issued by sts.windows.net, not by
    the v2.0 endpoint the sign-in went through. Accepting both means the API
    works whether or not that manifest field has been set to 2, instead of
    rejecting every token with an issuer mismatch that looks nothing like a
    configuration problem. Setting it to 2 is still the right thing to do; see
    README "Entra ID SSO".
    """
    tid = settings.auth_tenant_id
    return {
        f"https://login.microsoftonline.com/{tid}/v2.0",
        f"https://sts.windows.net/{tid}/",
    }


def _valid_audiences() -> set[str]:
    """Entra issues `aud` as the bare client id for v2 tokens and as the
    Application ID URI for v1 ones. Which you get follows from the token
    version, so both are accepted for the same reason the issuers are."""
    cid = settings.auth_client_id
    return {cid, f"api://{cid}"}


_jwk_client: jwt.PyJWKClient | None = None
_jwk_lock = threading.Lock()


def _jwks() -> jwt.PyJWKClient:
    """One cached client for the process.

    PyJWKClient caches the key set for `lifespan` seconds and re-fetches on a
    key id it has not seen, which is exactly the behaviour a rotating JWKS
    needs: no request pays for a fetch except the first after a rotation.
    """
    global _jwk_client
    with _jwk_lock:
        if _jwk_client is None:
            _jwk_client = jwt.PyJWKClient(
                f"{_authority()}/discovery/v2.0/keys",
                cache_jwk_set=True,
                lifespan=settings.auth_jwks_cache_seconds,
            )
        return _jwk_client


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# auto_error=False so a missing header reaches our own handler and produces a
# 401 carrying WWW-Authenticate, rather than FastAPI's bare 403.
_bearer = HTTPBearer(auto_error=False)


def verify_token(token: str) -> dict:
    """Return the validated claims, or raise.

    Signature, issuer, audience and expiry are all checked. Nothing here trusts
    a claim before the signature has been verified against the tenant's keys.
    """
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as exc:
        # Reaching Microsoft failed, or the key id is unknown. That is this
        # service being unable to answer, not the caller being unauthenticated,
        # and a 503 says so where a 401 would send them round the login loop.
        log.warning("Could not resolve Entra signing key: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot reach the identity provider's signing keys",
        ) from exc

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=list(_valid_audiences()),
            leeway=settings.auth_leeway_seconds,
            # Checked below against a set, which older PyJWT cannot express here.
            options={"verify_iss": False, "require": ["exp", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise _unauthorized("Token was not issued for this application") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"Invalid token: {exc}") from exc

    if claims.get("iss") not in _valid_issuers():
        raise _unauthorized("Token was not issued by the configured tenant")

    # Guest accounts from another tenant carry a `tid` that is not ours even
    # when the issuer is, so this is a separate check rather than a corollary.
    if claims.get("tid") != settings.auth_tenant_id:
        raise _unauthorized("Token was not issued by the configured tenant")

    # This must be an *access token minted for this API*, not merely a token
    # carrying the right audience. An ID token from the same registration has
    # the same `aud`, `iss` and `tid`, and carries `roles` too when the user is
    # assigned one - so every check below would pass and a sign-in token would
    # work as an API credential. `scp` is the discriminator: Entra sets it on
    # delegated access tokens and never on ID tokens.
    #
    # This matters most where one app registration serves more than one
    # application, because then the replayed token is one a *different* app
    # legitimately holds.
    scope = settings.auth_api_scope
    if scope and scope not in (claims.get("scp") or "").split():
        raise _unauthorized(
            "Token is not an access token for this API "
            f"(no {scope} scope); an ID token will not do"
        )

    required = settings.auth_required_role
    if required and required not in (claims.get("roles") or []):
        # 403, not 401: they proved who they are and the answer is still no, so
        # sending them back through login would achieve nothing.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is not assigned the {required} role for this application",
        )

    return claims


class Principal:
    """Who is making the request. Not persisted - there is no user table."""

    def __init__(self, claims: dict):
        self.claims = claims
        self.object_id: str | None = claims.get("oid")
        self.name: str | None = claims.get("name")
        self.username: str | None = (
            claims.get("preferred_username") or claims.get("upn") or claims.get("email")
        )
        self.roles: list[str] = list(claims.get("roles") or [])

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<Principal {self.username or self.object_id}>"


ANONYMOUS = Principal({"name": "local", "preferred_username": "local"})


def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Router-level dependency guarding every data endpoint."""
    if not auth_enabled():
        return ANONYMOUS
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Not authenticated")
    principal = Principal(verify_token(credentials.credentials))
    # Handy for anything downstream that wants the caller without re-declaring
    # the dependency (exception handlers, logging middleware).
    request.state.principal = principal
    return principal
