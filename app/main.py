from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from app.tools.common import ExternalAPIError, error_payload, get_logger
from app.tools.crypto import get_crypto_price_data
from app.tools.currency import convert_currency_value
from app.tools.insights import financial_insights
from app.tools.stock import get_stock_quote
from app.tools.transactions import (
    flag_transaction_anomalies,
    list_seed_transactions,
    spending_summary,
)

APP_NAME = "financial-data-mcp"

# FastAPI app is useful for health checks and optional HTTP hosting.
app = FastAPI(title=APP_NAME)
mcp = FastMCP(APP_NAME)
logger = get_logger(__name__)


def _run_tool(tool_name: str, fn, source: str) -> dict:
    try:
        return fn()
    except ValueError as exc:
        logger.warning("Validation error in %s: %s", tool_name, exc)
        return error_payload(str(exc), source=source, error_type="validation_error")
    except ExternalAPIError as exc:
        logger.error("External API error in %s: %s", tool_name, exc)
        return error_payload(
            str(exc),
            source=getattr(exc, "source", source),
            error_type="upstream_error",
        )
    except Exception as exc:
        logger.exception("Unhandled error in %s", tool_name)
        return error_payload(
            f"Unexpected error in {tool_name}: {exc}",
            source=source,
            error_type="internal_error",
        )


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok", "service": APP_NAME}


@mcp.tool(name="convert_currency")
def convert_currency(from_currency: str, to_currency: str, amount: float) -> dict:
    return _run_tool(
        "convert_currency",
        lambda: convert_currency_value(
            from_currency=from_currency,
            to_currency=to_currency,
            amount=amount,
        ),
        source="exchange_rate",
    )


@mcp.tool(name="get_crypto_price")
def get_crypto_price(asset: str, vs_currency: str = "usd") -> dict:
    return _run_tool(
        "get_crypto_price",
        lambda: get_crypto_price_data(asset=asset, vs_currency=vs_currency),
        source="coingecko",
    )


@mcp.tool(name="list_transactions")
def list_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> dict:
    return _run_tool(
        "list_transactions",
        lambda: list_seed_transactions(
            start_date=start_date,
            end_date=end_date,
            category=category,
            limit=limit,
        ),
        source="transactions",
    )


@mcp.tool(name="get_spending_summary")
def get_spending_summary(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    return _run_tool(
        "get_spending_summary",
        lambda: spending_summary(start_date=start_date, end_date=end_date),
        source="transactions",
    )


@mcp.tool(name="flag_anomalies")
def flag_anomalies(
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
) -> dict:
    return _run_tool(
        "flag_anomalies",
        lambda: flag_transaction_anomalies(
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount,
        ),
        source="transactions",
    )


@mcp.tool(name="financial_insights")
def get_financial_insights(
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
) -> dict:
    return _run_tool(
        "financial_insights",
        lambda: financial_insights(
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount,
        ),
        source="insights",
    )


@mcp.tool(name="get_stock_quote")
def get_stock_price(symbol: str, api_key: str | None = None) -> dict:
    return _run_tool(
        "get_stock_quote",
        lambda: get_stock_quote(symbol=symbol, api_key=api_key),
        source="alphavantage",
    )


if __name__ == "__main__":
    mcp.run()
