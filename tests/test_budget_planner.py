from __future__ import annotations

import pytest

from app.tools.budget_planner import plan_savings
from app.tools.common import IngestionRequiredError, TRANSACTION_STORE
from app.tools.transactions import set_ingested_transactions


def _create_session() -> str:
    return TRANSACTION_STORE.create_session()


def _planner_sample_transactions() -> list[dict]:
    return [
        {
            "id": "m1_rent",
            "date": "2026-02-01",
            "merchant": "Landlord LLC",
            "category": "rent",
            "amount": 1600.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m1_food",
            "date": "2026-02-05",
            "merchant": "Fresh Mart",
            "category": "food",
            "amount": 320.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m1_ent",
            "date": "2026-02-10",
            "merchant": "Movies",
            "category": "entertainment",
            "amount": 180.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m2_rent",
            "date": "2026-03-01",
            "merchant": "Landlord LLC",
            "category": "rent",
            "amount": 1600.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m2_food",
            "date": "2026-03-05",
            "merchant": "Fresh Mart",
            "category": "food",
            "amount": 280.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m2_ent",
            "date": "2026-03-12",
            "merchant": "Concerts",
            "category": "entertainment",
            "amount": 220.0,
            "currency": "USD",
            "direction": "debit",
        },
    ]


def test_budget_planner_requires_ingestion() -> None:
    session_id = _create_session()
    with pytest.raises(IngestionRequiredError, match="ingest_financial_documents"):
        plan_savings(session_id=session_id)


def test_budget_planner_returns_target_feasibility_and_recommendations() -> None:
    session_id = _create_session()
    set_ingested_transactions(
        transactions=_planner_sample_transactions(),
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
    session_id = _create_session()
    set_ingested_transactions(
        transactions=_planner_sample_transactions(),
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
    session_id = _create_session()
    set_ingested_transactions(
        transactions=_planner_sample_transactions()[:3],
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    result = plan_savings(session_id=session_id)
    assert result["months_of_history"] == 1
    assert result["warnings"]
