from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from app.tools.crypto import get_crypto_price_data
from app.tools.currency import convert_currency_value
from app.tools.transactions import (
    flag_transaction_anomalies,
    list_seed_transactions,
    spending_summary,
)

APP_NAME = "financial-data-mcp"

# FastAPI app is useful for health checks and optional HTTP hosting.
app = FastAPI(title=APP_NAME)
mcp = FastMCP(APP_NAME)


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok", "service": APP_NAME}


@mcp.tool(name="convert_currency")
def convert_currency(from_currency: str, to_currency: str, amount: float) -> dict:
    return convert_currency_value(
        from_currency=from_currency,
        to_currency=to_currency,
        amount=amount,
    )


@mcp.tool(name="get_crypto_price")
def get_crypto_price(asset: str, vs_currency: str = "usd") -> dict:
    return get_crypto_price_data(asset=asset, vs_currency=vs_currency)


@mcp.tool(name="list_transactions")
def list_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> dict:
    return list_seed_transactions(
        start_date=start_date,
        end_date=end_date,
        category=category,
        limit=limit,
    )


@mcp.tool(name="get_spending_summary")
def get_spending_summary(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    return spending_summary(start_date=start_date, end_date=end_date)


@mcp.tool(name="flag_anomalies")
def flag_anomalies(
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
) -> dict:
    return flag_transaction_anomalies(
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
    )


if __name__ == "__main__":
    mcp.run()
