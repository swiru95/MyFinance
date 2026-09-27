"""The harness itself: the app boots on a throwaway database, offline."""


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_settings_default_to_pln(client):
    assert client.get("/api/settings").json()["base_currency"] == "PLN"


def test_prices_come_from_fallbacks(client):
    body = client.get("/api/summary").json()
    assert body["total_value"] == 0
    assert body["crypto_prices"]["BTC"] > 0
