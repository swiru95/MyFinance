"""Client for the local llama-server (OpenAI-compatible chat completions).

Deliberately thin: one blocking call, no streaming. The caller already runs on
a worker thread because generation takes minutes, so there is nothing for
async to overlap with here.
"""
from __future__ import annotations

import os
import ssl

import httpx

from ..config import settings


class LLMUnavailable(RuntimeError):
    """No model is configured, or the server could not be reached."""


def using_mtls() -> bool:
    """Whether a client certificate is configured and actually present.

    Checked on disk rather than trusted from config: autocert writes the pair
    into the pod after the container starts, so a path that is set but not yet
    populated means "not ready", not "misconfigured".
    """
    return bool(
        settings.llm_client_cert
        and settings.llm_client_key
        and os.path.exists(settings.llm_client_cert)
        and os.path.exists(settings.llm_client_key)
    )


def configured() -> bool:
    """Whether the assessment feature has somewhere to send a request.

    The API key is required even with mutual TLS. A certificate authenticates
    this backend to the llama-server *router*, but the router does not pass
    that identity on to the model child process it proxies inference to, so a
    certificate alone reaches /slots and not /v1/chat/completions. Measured
    2026-09-17; see the note in that server's config.yaml.

    The certificate is still doing real work: where both are presented the
    router authorizes on the certificate, so the key should be scoped to the
    same least-privilege role rather than being an admin key.
    """
    return bool(settings.llm_base_url and settings.llm_api_key)


def _ssl_context() -> ssl.SSLContext | bool:
    """How this client proves who it is, and who it is willing to talk to.

    Rebuilt per request on purpose. autocert renews the certificate in place
    while the pod runs, and a context built once at import would pin the pair
    that existed at startup and start failing handshakes the day it rotates.
    Generating a report is a minutes-long operation that happens rarely, so
    re-reading two small files each time costs nothing.
    """
    if not settings.llm_ca_bundle:
        # No bundle to verify against. Without a client certificate there is
        # nothing to configure beyond the on/off flag.
        if not using_mtls():
            return settings.llm_verify_tls
        context = ssl.create_default_context()
        if not settings.llm_verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
    else:
        if not os.path.exists(settings.llm_ca_bundle):
            raise LLMUnavailable(
                f"CA bundle {settings.llm_ca_bundle} is missing; "
                f"cannot verify the model server."
            )
        context = ssl.create_default_context(cafile=settings.llm_ca_bundle)

    if using_mtls():
        try:
            context.load_cert_chain(
                certfile=settings.llm_client_cert,
                keyfile=settings.llm_client_key,
                password=settings.llm_client_key_password or None,
            )
        except (ssl.SSLError, OSError) as exc:
            raise LLMUnavailable(f"Could not load the client certificate: {exc}") from exc
    return context


def complete(
    model: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Run one chat completion and return the assistant's text.

    Reasoning models answer with `reasoning_content` alongside `content`. Only
    `content` is returned: the chain of thought is the model working, not the
    report, and storing it would bury the actual assessment.
    """
    if not configured():
        raise LLMUnavailable("No model configured")

    url = settings.llm_base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    try:
        with httpx.Client(timeout=settings.llm_timeout, verify=_ssl_context()) as client:
            res = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMUnavailable(f"Could not reach the model server: {exc}") from exc

    if res.status_code != 200:
        # The body carries the server's own reason (an unknown model name, a
        # prompt past the context window); the status alone would not.
        raise LLMUnavailable(f"Model server returned {res.status_code}: {res.text[:300]}")

    try:
        choice = res.json()["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMUnavailable("Model server returned an unexpected response") from exc

    text = (message.get("content") or "").strip()
    if not text:
        # A reasoning model spends one budget on reasoning *and* answer, so too
        # small a max_tokens comes back as empty content with finish_reason
        # "length" - which would otherwise be stored as a blank report that
        # looks like a success. Name the actual cause: the two failures here
        # have different fixes.
        if choice.get("finish_reason") == "length":
            raise LLMUnavailable(
                f"{model} used its whole {max_tokens}-token budget on reasoning "
                f"and produced no report. Raise MYFINANCE_LLM_MAX_TOKENS."
            )
        raise LLMUnavailable(f"{model} returned no text.")
    return text
