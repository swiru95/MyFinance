"""TLS to the model server: verified unless switched off."""
import httpx
import pytest

from src.config import Settings, settings
from src.services import llm


def test_verification_is_on_by_default():
    assert Settings.model_fields["llm_verify_tls"].default is True


def test_flag_is_passed_through_without_bundle_or_client_cert(monkeypatch):
    monkeypatch.setattr(settings, "llm_ca_bundle", "")
    monkeypatch.setattr(settings, "llm_client_cert", "")
    monkeypatch.setattr(settings, "llm_verify_tls", True)
    assert llm._ssl_context() is True
    monkeypatch.setattr(settings, "llm_verify_tls", False)
    assert llm._ssl_context() is False


def test_verify_failure_names_the_fix(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://model.invalid")
    monkeypatch.setattr(settings, "llm_api_key", "k")

    def boom(self, *a, **kw):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    monkeypatch.setattr(httpx.Client, "post", boom)
    with pytest.raises(llm.LLMUnavailable, match="MYFINANCE_LLM_CA_BUNDLE"):
        llm.complete("m", "s", "u")
