from __future__ import annotations

import pytest

from app.tools.budget_planner import plan_savings
from app.tools.common import IngestionRequiredError, TRANSACTION_STORE
from app.tools.transactions import set_ingested_transactions
from tests.helpers import create_session, planner_sample_transactions


def test_budget_planner_requires_ingestion() -> None:
    session_id = create_session()
    with pytest.raises(IngestionRequiredError, match="ingest_financial_documents"):
        plan_savings(session_id=session_id)


def test_budget_planner_returns_target_feasibility_and_recommendations() -> None:
    session_id = create_session()
    set_ingested_transactions(
        transactions=planner_sample_transactions(),
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    result = plan_savings(session_id=session_id, target_amount=200.0, strategy="balanced")

    assert result["months_of_history"] == 2
    assert result["max_savings_estimate"] > 0
    assert isinstance(result["target_met"], bool)
    assert result["target_amount"] == 200.0
    assert len(result["recommendations"]) > 0
    assert any(item["category"] == "entertainment" for item in result["recommendations"])


def test_budget_planner_max_savings_without_target() -> None:
    session_id = create_session()
    set_ingested_transactions(
        transactions=planner_sample_transactions(),
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    result = plan_savings(session_id=session_id, strategy="aggressive")

    assert result["target_amount"] is None
    assert result["target_met"] is True
    assert result["max_savings_estimate"] >= 250.0
    assert result["projected_monthly_spend"] < result["baseline_monthly_spend"]


def test_budget_planner_warns_on_limited_history() -> None:
    session_id = create_session()
    set_ingested_transactions(
        transactions=planner_sample_transactions()[:3],
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    result = plan_savings(session_id=session_id)
    assert result["months_of_history"] == 1
    assert result["warnings"]
