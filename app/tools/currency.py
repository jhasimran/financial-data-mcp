from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.tools.common import ExternalAPIError

EXCHANGE_RATE_BASE_URL = "https://open.er-api.com/v6/latest"


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

    try:
        response = httpx.get(f"{EXCHANGE_RATE_BASE_URL}/{source}", timeout=12.0)
    except httpx.HTTPError as exc:
        raise ExternalAPIError("Failed to reach ExchangeRate API.") from exc

    if response.status_code != 200:
        raise ExternalAPIError(
            f"ExchangeRate API returned status code {response.status_code}."
        )

    payload = response.json()
    if payload.get("result") != "success":
        raise ExternalAPIError("ExchangeRate API returned a non-success result.")

    rates = payload.get("rates")
    if not isinstance(rates, dict) or target not in rates:
        raise ExternalAPIError(f"Target currency '{target}' is not available.")

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
    }
