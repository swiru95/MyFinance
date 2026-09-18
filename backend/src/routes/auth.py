"""Authentication discovery and whoami.

`/api/auth/config` is deliberately unauthenticated: it is what the browser
reads *before* it has a token, to find out which tenant to sign in against.

It exists at all because `next build` bakes NEXT_PUBLIC_* variables into the
image, and the images here are built once in CI and deployed by Helm to a
cluster that decides its own tenant and client id. Serving those two values
from the backend keeps them in the chart's values file with everything else,
instead of pinning an app registration to an image tag. Nothing secret is
exposed by doing so - a public client's id and tenant are public by design, and
both travel in the browser's address bar during sign-in anyway.
"""
from fastapi import APIRouter, Depends

from ..auth import Principal, scope_uri, auth_enabled, require_user
from ..config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
def auth_config() -> dict:
    """What the SPA needs to construct its MSAL instance."""
    if not auth_enabled():
        return {"enabled": False}
    return {
        "enabled": True,
        "tenant_id": settings.auth_tenant_id,
        "client_id": settings.auth_client_id,
        "authority": f"https://login.microsoftonline.com/{settings.auth_tenant_id}",
        "scopes": [scope_uri()],
    }


@router.get("/me")
def me(principal: Principal = Depends(require_user)) -> dict:
    """The caller as this API sees them. Useful for confirming a deployment is
    really validating tokens rather than waving them through."""
    return {
        "authenticated": auth_enabled(),
        "object_id": principal.object_id,
        "name": principal.name,
        "username": principal.username,
        "roles": principal.roles,
    }
