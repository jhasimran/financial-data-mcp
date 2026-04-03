import pytest

from app.tools.common import ExternalAPIError
from app.tools.stock import get_stock_quote


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_get_stock_quote_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params: dict, timeout: float) -> DummyResponse:
        assert params["function"] == "GLOBAL_QUOTE"
        assert timeout == 12.0
        return DummyResponse(200, {"Global Quote": {"05. price": "182.31"}})

    monkeypatch.setattr("app.tools.stock.httpx.get", fake_get)
    result = get_stock_quote("AAPL", api_key="demo")
    assert result["symbol"] == "AAPL"
    assert result["price"] == 182.31
    assert result["source"] == "alphavantage.co"
    assert result["cache_hit"] is False


def test_get_stock_quote_invalid_symbol() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        get_stock_quote("   ")


def test_get_stock_quote_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params: dict, timeout: float) -> DummyResponse:
        return DummyResponse(500, {})

    monkeypatch.setattr("app.tools.stock.httpx.get", fake_get)
    with pytest.raises(ExternalAPIError, match="status code 500"):
        get_stock_quote("TSLA", api_key="demo")
