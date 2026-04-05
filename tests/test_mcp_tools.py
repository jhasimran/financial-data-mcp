from __future__ import annotations

from app.main import get_savings_plan, ingest_documents
from app.tools.transactions import clear_ingested_transactions
from tests.helpers import fake_ingest_result, planner_sample_transactions


def test_mcp_plan_savings_requires_ingestion() -> None:
    clear_ingested_transactions()

    result = get_savings_plan()

    assert result["ok"] is False
    assert result["type"] == "ingestion_required"


def test_mcp_plan_savings_reads_default_session_data() -> None:
    clear_ingested_transactions()
    from app.tools.transactions import set_ingested_transactions

    set_ingested_transactions(
        transactions=planner_sample_transactions(),
        sources=1,
        warnings=[],
    )

    result = get_savings_plan(target_amount=200.0, strategy="balanced")

    assert result["target_amount"] == 200.0
    assert result["max_savings_estimate"] > 0
    assert result["recommendations"]


def test_mcp_ingestion_and_plan_savings_share_default_session(monkeypatch) -> None:
    clear_ingested_transactions()
    monkeypatch.setattr("app.main.ingest_financial_documents", lambda file_paths: fake_ingest_result())

    ingest_result = ingest_documents(["statement.pdf"])
    savings_result = get_savings_plan(strategy="balanced")

    assert ingest_result["count"] == 2
    assert savings_result["max_savings_estimate"] > 0
