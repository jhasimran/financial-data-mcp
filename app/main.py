import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from app.api.orchestrator import router as orchestrator_router
from app.tools.budget_planner import plan_savings
from app.tools.common import (
    ExternalAPIError,
    IngestionRequiredError,
    error_payload,
    get_logger,
)
from app.tools.crypto import get_crypto_price_data
from app.tools.currency import convert_currency_value
from app.tools.ingestion import ingest_financial_documents
from app.tools.insights import financial_insights
from app.tools.stock import get_stock_quote
from app.tools.transactions import (
    set_ingested_transactions,
    flag_transaction_anomalies,
    list_seed_transactions,
    spending_summary,
)

APP_NAME = "financial-data-mcp"

# FastAPI app is useful for health checks and optional HTTP hosting.
app = FastAPI(title=APP_NAME)
mcp = FastMCP(APP_NAME)
logger = get_logger(__name__)

origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(orchestrator_router)


def _run_tool(tool_name: str, fn, source: str) -> dict:
    try:
        return fn()
    except IngestionRequiredError:
        logger.warning("Ingestion required for tool=%s", tool_name)
        return error_payload(
            "No ingested transactions available. Run ingest_financial_documents first.",
            source="ingestion",
            error_type="ingestion_required",
        )
    except ValueError as exc:
        logger.warning("Validation error in tool=%s", tool_name)
        return error_payload(
            str(exc),
            source=source,
            error_type="validation_error",
        )
    except ExternalAPIError as exc:
        logger.error("External API error in tool=%s source=%s", tool_name, source)
        return error_payload(
            str(exc),
            source=getattr(exc, "source", source),
            error_type="upstream_error",
        )
    except Exception:
        logger.exception("Unhandled error in tool=%s", tool_name)
        return error_payload(
            f"Unexpected failure in {tool_name}.",
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


@mcp.tool(name="plan_savings")
def get_savings_plan(
    target_amount: float | None = None,
    strategy: str = "balanced",
) -> dict:
    return _run_tool(
        "plan_savings",
        lambda: plan_savings(
            session_id="default",
            target_amount=target_amount,
            strategy=strategy,
        ),
        source="budget_planner",
    )


@mcp.tool(name="get_stock_quote")
def get_stock_price(symbol: str, api_key: str | None = None) -> dict:
    return _run_tool(
        "get_stock_quote",
        lambda: get_stock_quote(symbol=symbol, api_key=api_key),
        source="alphavantage",
    )


@mcp.tool(name="ingest_financial_documents")
def ingest_documents(file_paths: list[str]) -> dict:
    def _ingest() -> dict:
        result = ingest_financial_documents(file_paths=file_paths)
        set_ingested_transactions(
            transactions=result["transactions"],
            sources=result["sources"],
            warnings=result["warnings"],
        )
        return result

    return _run_tool(
        "ingest_financial_documents",
        _ingest,
        source="ingestion",
    )


if __name__ == "__main__":
    mcp.run()
