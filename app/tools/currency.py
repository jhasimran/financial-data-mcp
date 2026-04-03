from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.tools.common import ExternalAPIError, TTLCache, get_logger

EXCHANGE_RATE_BASE_URL = "https://open.er-api.com/v6/latest"
CURRENCY_CACHE = TTLCache(ttl_seconds=120)
logger = get_logger(__name__)


def _validate_currency_code(code: str, field_name: str) -> str:
    normalized = code.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError(f"{field_name} must be a 3-letter ISO currency code.")
    return normalized


def _parse_rate_date(payload: dict) -> str:
    timestamp = payload.get("time_last_update_utc")
    if isinstance(timestamp, str):
        try:
            parsed = datetime.strptime(timestamp, "%a, %d %b %Y %H:%M:%S +0000")
            return parsed.date().isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def convert_currency_value(from_currency: str, to_currency: str, amount: float) -> dict:
    if amount < 0:
        raise ValueError("amount must be non-negative.")

    source = _validate_currency_code(from_currency, "from_currency")
    target = _validate_currency_code(to_currency, "to_currency")

    cache_key = f"rates:{source}"
    cached = CURRENCY_CACHE.get(cache_key)
    if cached is not None:
        payload = cached
        cache_hit = True
    else:
        logger.info("Fetching ExchangeRate data for base=%s", source)
        try:
            response = httpx.get(f"{EXCHANGE_RATE_BASE_URL}/{source}", timeout=12.0)
        except httpx.TimeoutException as exc:
            logger.exception("ExchangeRate API timed out for base=%s", source)
            raise ExternalAPIError("ExchangeRate API timed out.", source="exchange_rate") from exc
        except httpx.HTTPError as exc:
            logger.exception("ExchangeRate API request failed for base=%s", source)
            raise ExternalAPIError(
                "Failed to reach ExchangeRate API.", source="exchange_rate"
            ) from exc

        if response.status_code != 200:
            logger.error("ExchangeRate API returned status=%s", response.status_code)
            raise ExternalAPIError(
                f"ExchangeRate API returned status code {response.status_code}.",
                source="exchange_rate",
            )
        payload = response.json()
        CURRENCY_CACHE.set(cache_key, payload)
        cache_hit = False

    if payload.get("result") != "success":
        raise ExternalAPIError(
            "ExchangeRate API returned a non-success result.", source="exchange_rate"
        )

    rates = payload.get("rates")
    if not isinstance(rates, dict) or target not in rates:
        raise ExternalAPIError(
            f"Target currency '{target}' is not available.", source="exchange_rate"
        )

    rate = float(rates[target])
    converted = round(amount * rate, 2)

    return {
        "from_currency": source,
        "to_currency": target,
        "amount": round(float(amount), 2),
        "converted": converted,
        "rate": rate,
        "rate_date": _parse_rate_date(payload),
        "source": "open.er-api.com",
        "cache_hit": cache_hit,
    }
