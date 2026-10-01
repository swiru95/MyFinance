"""A fake OpenID Connect issuer for tests: a local RSA key, a JWKS and a
discovery document, served by replacing `auth._fetch_json` so nothing touches
the network. Tokens it signs are genuine RS256 JWTs and go through the real
validation code."""
from __future__ import annotations

import json
import time

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://idp.test/realms/lab"
AUDIENCE = "myfinance-api"
JWKS_URI = f"{ISSUER}/protocol/openid-connect/certs"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"

PEPPER = "test-pepper-0123456789abcdef0123456789abcdef"

# Generating an RSA key is the slow part; one per process is plenty. A second,
# unrelated key is for tokens that must fail signature checks.
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeIdP:
    def __init__(self) -> None:
        self.kid = "key-1"
        self.down = False
        self.fetched: list[str] = []
        self.published = [(self.kid, _KEY)]

    def jwks(self) -> dict:
        keys = []
        for kid, key in self.published:
            jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
            jwk.update(kid=kid, use="sig", alg="RS256")
            keys.append(jwk)
        return {"keys": keys}

    def discovery(self) -> dict:
        return {"issuer": ISSUER, "jwks_uri": JWKS_URI}

    def fetch(self, url: str) -> dict:
        self.fetched.append(url)
        if self.down:
            raise httpx.ConnectError("idp is down")
        if url == DISCOVERY_URL:
            return self.discovery()
        if url == JWKS_URI:
            return self.jwks()
        raise httpx.HTTPStatusError(
            "404", request=httpx.Request("GET", url), response=httpx.Response(404)
        )

    def token(
        self,
        sub: str = "sub-alice",
        *,
        iss: str = ISSUER,
        aud=AUDIENCE,
        ttl: int = 3600,
        key=None,
        kid: str | None = None,
        typ: str | None = "at+jwt",
        drop: tuple[str, ...] = (),
        **claims,
    ) -> str:
        now = int(time.time())
        body = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + ttl, **claims}
        for name in drop:
            body.pop(name, None)
        # `typ` defaults to what RFC 9068 access tokens carry. None leaves the
        # header without one; "JWT" is what an ID token typically has.
        return jwt.encode(
            body, key or _KEY, algorithm="RS256", headers={"kid": kid or self.kid, "typ": typ}
        )

    @staticmethod
    def foreign_key():
        """A key the issuer does not publish."""
        return _OTHER_KEY

    def rotate(self, new_kid: str) -> None:
        """Publish a different key id, as an issuer does when it rotates."""
        self.kid = new_kid
        self.published = [(new_kid, _KEY)]
