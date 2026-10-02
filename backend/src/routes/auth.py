"""Authentication discovery and whoami.

`/api/auth/config` is deliberately unauthenticated: it is what the browser
reads *before* it has a token, to find out which provider to sign in against.

It exists at all because `next build` bakes NEXT_PUBLIC_* variables into the
image, and the images here are built once in CI and deployed by Helm to a
cluster that decides its own tenant and client id. Serving those values from
the backend keeps them in the chart's values file with everything else, instead
of pinning an app registration to an image tag. Nothing secret is exposed by
doing so - a public client's id and issuer are public by design, and both
travel in the browser's address bar during sign-in anyway.
"""
from fastapi import APIRouter, Depends

from ..auth import Principal, audiences, auth_enabled, issuer, require_user, scope_uri
from ..config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
def auth_config() -> dict:
    """What the SPA needs to construct its sign-in client."""
    if not auth_enabled():
        return {"enabled": False}
    config: dict = {
        "enabled": True,
        "issuer": issuer(),
        "audience": audiences(),
        "client_id": settings.auth_client_id,
        "scopes": [scope_uri()] if scope_uri() else [],
    }
    if settings.auth_tenant_id:
        # Entra: the SPA's MSAL client wants an authority, not an issuer.
        config["tenant_id"] = settings.auth_tenant_id
        config["authority"] = f"https://login.microsoftonline.com/{settings.auth_tenant_id}"
    return config


@router.get("/me")
def me(principal: Principal = Depends(require_user)) -> dict:
    """The caller as this API sees them: an opaque id and nothing about the
    person. Display name and email are not known here and not returned - the
    browser reads them from its own token. Useful for confirming a deployment
    is really validating tokens rather than waving them through."""
    return {
        "authenticated": auth_enabled(),
        "user_id": str(principal.user_id),
    }
