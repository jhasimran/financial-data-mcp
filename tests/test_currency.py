import pytest

from app.tools.common import ExternalAPIError
from app.tools.currency import convert_currency_value


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_convert_currency_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> DummyResponse:
        assert "USD" in url
        assert timeout == 12.0
        return DummyResponse(
            200,
            {
                "result": "success",
                "time_last_update_utc": "Mon, 31 Mar 2026 00:00:01 +0000",
                "rates": {"EUR": 0.925},
            },
        )

    monkeypatch.setattr("app.tools.currency.httpx.get", fake_get)

    result = convert_currency_value("usd", "eur", 100)

    assert result["converted"] == 92.5
    assert result["rate"] == 0.925
    assert result["rate_date"] == "2026-03-31"
    assert result["from_currency"] == "USD"
    assert result["to_currency"] == "EUR"
    assert result["cache_hit"] is False


def test_convert_currency_invalid_currency() -> None:
    with pytest.raises(ValueError, match="3-letter ISO currency code"):
        convert_currency_value("US", "EUR", 10)


def test_convert_currency_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> DummyResponse:
        return DummyResponse(503, {})

    monkeypatch.setattr("app.tools.currency.httpx.get", fake_get)

    with pytest.raises(ExternalAPIError, match="status code 503"):
        convert_currency_value("GBP", "EUR", 100)
