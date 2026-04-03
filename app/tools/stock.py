from __future__ import annotations

import os

import httpx

from app.tools.common import ExternalAPIError, TTLCache, get_logger

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
CACHE = TTLCache(ttl_seconds=60)
logger = get_logger(__name__)


def get_stock_quote(symbol: str, api_key: str | None = None) -> dict:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")

    token = api_key or os.getenv("ALPHAVANTAGE_API_KEY", "demo")
    cache_key = f"{normalized}:{token == 'demo'}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        cached["cache_hit"] = True
        return cached

    logger.info("Fetching stock quote symbol=%s", normalized)
    try:
        response = httpx.get(
            ALPHA_VANTAGE_URL,
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": normalized,
                "apikey": token,
            },
            timeout=12.0,
        )
    except httpx.TimeoutException as exc:
        logger.exception("Alpha Vantage timeout symbol=%s", normalized)
        raise ExternalAPIError("Alpha Vantage API timed out.", source="alphavantage") from exc
    except httpx.HTTPError as exc:
        logger.exception("Alpha Vantage request failure symbol=%s", normalized)
        raise ExternalAPIError(
            "Failed to reach Alpha Vantage API.",
            source="alphavantage",
        ) from exc

    if response.status_code != 200:
        raise ExternalAPIError(
            f"Alpha Vantage API returned status code {response.status_code}.",
            source="alphavantage",
        )

    payload = response.json()
    quote = payload.get("Global Quote", {})
    raw_price = quote.get("05. price")
    if not raw_price:
        raise ExternalAPIError(
            "Alpha Vantage did not return a valid quote. "
            "Provide ALPHAVANTAGE_API_KEY for non-demo symbols.",
            source="alphavantage",
        )

    result = {
        "symbol": normalized,
        "price": float(raw_price),
        "currency": "USD",
        "source": "alphavantage.co",
        "cache_hit": False,
    }
    CACHE.set(cache_key, result.copy())
    return result


def not_implemented_stock_tool() -> dict:
    return {
        "status": "not_implemented",
        "message": "Stock tooling is intentionally deferred beyond V1.",
    }
