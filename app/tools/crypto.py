from __future__ import annotations

import httpx

from app.tools.common import ExternalAPIError

COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
ASSET_ALIASES = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
}


def _normalize_asset_id(asset: str) -> str:
    normalized = asset.strip().lower()
    if not normalized:
        raise ValueError("asset must not be empty.")
    return ASSET_ALIASES.get(normalized, normalized)


def _normalize_vs_currency(vs_currency: str) -> str:
    normalized = vs_currency.strip().lower()
    if len(normalized) < 3 or not normalized.isalpha():
        raise ValueError("vs_currency must be an alphabetic currency code.")
    return normalized


def get_crypto_price_data(asset: str, vs_currency: str = "usd") -> dict:
    asset_id = _normalize_asset_id(asset)
    quote_currency = _normalize_vs_currency(vs_currency)

    try:
        response = httpx.get(
            COINGECKO_SIMPLE_PRICE_URL,
            params={"ids": asset_id, "vs_currencies": quote_currency},
            timeout=12.0,
        )
    except httpx.HTTPError as exc:
        raise ExternalAPIError("Failed to reach CoinGecko API.") from exc

    if response.status_code != 200:
        raise ExternalAPIError(f"CoinGecko API returned status code {response.status_code}.")

    payload = response.json()
    price_map = payload.get(asset_id)
    if not isinstance(price_map, dict) or quote_currency not in price_map:
        raise ExternalAPIError(
            f"CoinGecko did not return a price for '{asset_id}' in '{quote_currency}'."
        )

    return {
        "asset": asset_id,
        "vs_currency": quote_currency,
        "price": float(price_map[quote_currency]),
        "source": "coingecko.com",
    }
