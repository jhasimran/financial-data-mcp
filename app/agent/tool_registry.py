from __future__ import annotations

from typing import Any, Callable

from app.tools.crypto import get_crypto_price_data
from app.tools.currency import convert_currency_value
from app.tools.budget_planner import plan_savings
from app.tools.ingestion import ingest_financial_documents
from app.tools.insights import financial_insights
from app.tools.stock import get_stock_quote
from app.tools.transactions import (
    flag_transaction_anomalies,
    list_seed_transactions,
    spending_summary,
)

ToolFn = Callable[[dict[str, Any], str], dict[str, Any]]

TRANSACTION_TOOLS = {
    "list_transactions",
    "get_spending_summary",
    "flag_anomalies",
    "financial_insights",
    "plan_savings",
}


def _ingest(args: dict[str, Any], _session_id: str) -> dict[str, Any]:
    file_paths = args.get("file_paths")
    if not isinstance(file_paths, list) or not file_paths:
        raise ValueError("file_paths must be provided as a non-empty list.")
    return ingest_financial_documents(file_paths=file_paths)


def _list_transactions(args: dict[str, Any], session_id: str) -> dict[str, Any]:
    return list_seed_transactions(
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        category=args.get("category"),
        limit=int(args.get("limit", 20)),
        session_id=session_id,
    )


def _spending_summary(args: dict[str, Any], session_id: str) -> dict[str, Any]:
    return spending_summary(
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        session_id=session_id,
    )


def _flag_anomalies(args: dict[str, Any], session_id: str) -> dict[str, Any]:
    return flag_transaction_anomalies(
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        min_amount=args.get("min_amount"),
        session_id=session_id,
    )


def _financial_insights(args: dict[str, Any], session_id: str) -> dict[str, Any]:
    return financial_insights(
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        min_amount=args.get("min_amount"),
        session_id=session_id,
    )


def _convert_currency(args: dict[str, Any], _session_id: str) -> dict[str, Any]:
    return convert_currency_value(
        from_currency=str(args.get("from_currency", "")),
        to_currency=str(args.get("to_currency", "")),
        amount=float(args.get("amount", 0)),
    )


def _crypto_price(args: dict[str, Any], _session_id: str) -> dict[str, Any]:
    return get_crypto_price_data(
        asset=str(args.get("asset", "")),
        vs_currency=str(args.get("vs_currency", "usd")),
    )


def _stock_quote(args: dict[str, Any], _session_id: str) -> dict[str, Any]:
    api_key = args.get("api_key")
    if api_key is not None:
        api_key = str(api_key)
    return get_stock_quote(symbol=str(args.get("symbol", "")), api_key=api_key)


def _plan_savings(args: dict[str, Any], session_id: str) -> dict[str, Any]:
    target_amount = args.get("target_amount")
    strategy = str(args.get("strategy", "balanced"))
    parsed_target: float | None = None
    if target_amount is not None and target_amount != "":
        parsed_target = float(target_amount)
    return plan_savings(
        session_id=session_id,
        target_amount=parsed_target,
        strategy=strategy,
    )


TOOL_REGISTRY: dict[str, ToolFn] = {
    "ingest_financial_documents": _ingest,
    "list_transactions": _list_transactions,
    "get_spending_summary": _spending_summary,
    "flag_anomalies": _flag_anomalies,
    "financial_insights": _financial_insights,
    "convert_currency": _convert_currency,
    "get_crypto_price": _crypto_price,
    "get_stock_quote": _stock_quote,
    "plan_savings": _plan_savings,
}


def execute_tool(name: str, args: dict[str, Any], session_id: str) -> dict[str, Any]:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        raise ValueError(f"Unsupported tool '{name}'.")
    return fn(args, session_id)
