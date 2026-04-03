from __future__ import annotations

import httpx

from app.tools.common import ExternalAPIError, TTLCache, get_logger

COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
CACHE = TTLCache(ttl_seconds=60)
logger = get_logger(__name__)
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

    cache_key = f"{asset_id}:{quote_currency}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        payload = cached
        cache_hit = True
    else:
        logger.info("Fetching CoinGecko price for asset=%s vs=%s", asset_id, quote_currency)
        try:
            response = httpx.get(
                COINGECKO_SIMPLE_PRICE_URL,
                params={"ids": asset_id, "vs_currencies": quote_currency},
                timeout=12.0,
            )
        except httpx.TimeoutException as exc:
            logger.exception("CoinGecko API timed out asset=%s vs=%s", asset_id, quote_currency)
            raise ExternalAPIError("CoinGecko API timed out.", source="coingecko") from exc
        except httpx.HTTPError as exc:
            logger.exception("CoinGecko API request failed asset=%s vs=%s", asset_id, quote_currency)
            raise ExternalAPIError("Failed to reach CoinGecko API.", source="coingecko") from exc

        if response.status_code != 200:
            logger.error("CoinGecko API returned status=%s", response.status_code)
            raise ExternalAPIError(
                f"CoinGecko API returned status code {response.status_code}.",
                source="coingecko",
            )
        payload = response.json()
        CACHE.set(cache_key, payload)
        cache_hit = False

    price_map = payload.get(asset_id)
    if not isinstance(price_map, dict) or quote_currency not in price_map:
        raise ExternalAPIError(
            f"CoinGecko did not return a price for '{asset_id}' in '{quote_currency}'.",
            source="coingecko",
        )

    return {
        "asset": asset_id,
        "vs_currency": quote_currency,
        "price": float(price_map[quote_currency]),
        "source": "coingecko.com",
        "cache_hit": cache_hit,
    }
