import pytest

from app.tools.common import ExternalAPIError
from app.tools.crypto import get_crypto_price_data


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_get_crypto_price_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params: dict, timeout: float) -> DummyResponse:
        assert params == {"ids": "bitcoin", "vs_currencies": "usd"}
        assert timeout == 12.0
        return DummyResponse(200, {"bitcoin": {"usd": 45321.17}})

    monkeypatch.setattr("app.tools.crypto.httpx.get", fake_get)

    result = get_crypto_price_data("btc", "usd")

    assert result == {
        "asset": "bitcoin",
        "vs_currency": "usd",
        "price": 45321.17,
        "source": "coingecko.com",
    }


def test_get_crypto_price_validation() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        get_crypto_price_data("   ", "usd")


def test_get_crypto_price_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params: dict, timeout: float) -> DummyResponse:
        return DummyResponse(429, {})

    monkeypatch.setattr("app.tools.crypto.httpx.get", fake_get)

    with pytest.raises(ExternalAPIError, match="status code 429"):
        get_crypto_price_data("bitcoin", "usd")
