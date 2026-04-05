from __future__ import annotations

import re

from app.agent.run import run_langgraph_chat
from app.tools.common import TRANSACTION_STORE
from app.tools.transactions import set_ingested_transactions
from tests.helpers import create_session, fake_ingest_result


def test_langgraph_requires_transactions_for_analysis() -> None:
    session_id = create_session()
    result = run_langgraph_chat(session_id=session_id, question="show my spending summary")
    assert result["status"] == "needs_input"
    assert result["missing_input"] == "transactions"
    assert "upload" in result["answer"].lower()


def test_langgraph_ingests_attachments_inside_graph(monkeypatch) -> None:
    session_id = create_session()
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    monkeypatch.setattr("app.agent.nodes.ingest_financial_documents", lambda **_: fake_ingest_result())

    result = run_langgraph_chat(
        session_id=session_id,
        question="what are my top spending categories?",
        attachment_paths=["/tmp/statement.pdf"],
    )
    assert result["status"] == "done"
    assert "get_spending_summary" in result["tool_calls"]
    assert "get_spending_summary" in result["supporting_data"]
    assert TRANSACTION_STORE.has_data(session_id) is True


def test_langgraph_redacts_sensitive_tokens_in_supporting_data() -> None:
    session_id = create_session()
    set_ingested_transactions(
        transactions=[
            {
                "id": "tx1",
                "date": "2026-03-02",
                "merchant": "john@example.com 123456789 12 Main St",
                "category": "other",
                "amount": 42.0,
                "currency": "USD",
                "direction": "debit",
            }
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    result = run_langgraph_chat(session_id=session_id, question="list recent transactions")
    payload = str(result["supporting_data"])
    assert "john@example.com" not in payload
    assert re.search(r"\b\d{6,}\b", payload) is None
    assert "[redacted-email]" in payload


def test_langgraph_attachment_only_returns_follow_up_prompt(monkeypatch) -> None:
    session_id = create_session()
    monkeypatch.setattr("app.agent.nodes.ingest_financial_documents", lambda **_: fake_ingest_result())

    result = run_langgraph_chat(
        session_id=session_id,
        question="",
        attachment_paths=["/tmp/statement.pdf"],
    )
    assert result["status"] == "needs_input"
    assert result["missing_input"] == "question"
    assert "what would you like me to analyze next" in result["answer"].lower()


def test_langgraph_session_isolation() -> None:
    session_with_data = create_session()
    session_without_data = create_session()
    set_ingested_transactions(
        transactions=[
            {
                "id": "tx1",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1800.0,
                "currency": "USD",
                "direction": "debit",
            }
        ],
        sources=1,
        warnings=[],
        session_id=session_with_data,
    )

    ok_result = run_langgraph_chat(session_id=session_with_data, question="show summary")
    empty_result = run_langgraph_chat(session_id=session_without_data, question="show summary")

    assert ok_result["status"] == "done"
    assert empty_result["status"] == "needs_input"


def test_langgraph_routes_savings_target_queries_to_budget_planner(monkeypatch) -> None:
    session_id = create_session()
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    set_ingested_transactions(
        transactions=[
            {
                "id": "tx1",
                "date": "2026-02-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1500.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "tx2",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1500.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "tx3",
                "date": "2026-03-04",
                "merchant": "Fun Zone",
                "category": "entertainment",
                "amount": 220.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )

    result = run_langgraph_chat(
        session_id=session_id,
        question="How can I save 250 this month?",
    )
    assert result["status"] == "done"
    assert "plan_savings" in result["tool_calls"]
    assert "plan_savings" in result["supporting_data"]


def test_langgraph_multi_tool_plan_runs_multiple_transaction_tools(monkeypatch) -> None:
    session_id = create_session()
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    set_ingested_transactions(
        transactions=[
            {
                "id": "tx1",
                "date": "2026-02-12",
                "merchant": "Fresh Mart",
                "category": "food",
                "amount": 300.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "tx2",
                "date": "2026-03-12",
                "merchant": "Fresh Mart",
                "category": "food",
                "amount": 280.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )

    result = run_langgraph_chat(
        session_id=session_id,
        question="Summarize my spending and flag unusual transactions",
    )
    assert result["status"] == "done"
    assert "get_spending_summary" in result["tool_calls"]
    assert "flag_anomalies" in result["tool_calls"]
    assert result["answer"]


def test_langgraph_spending_categories_answer_includes_category_names(monkeypatch) -> None:
    session_id = create_session()
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    set_ingested_transactions(
        transactions=[
            {
                "id": "tx1",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1500.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "tx2",
                "date": "2026-03-02",
                "merchant": "Fresh Mart",
                "category": "food",
                "amount": 320.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )

    result = run_langgraph_chat(session_id=session_id, question="what are my top spending categories?")
    assert result["status"] == "done"
    assert "get_spending_summary" in result["tool_calls"]
    assert "rent" in result["answer"].lower() or "food" in result["answer"].lower()


def test_langgraph_savings_answer_includes_recommendation_detail(monkeypatch) -> None:
    session_id = create_session()
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    set_ingested_transactions(
        transactions=[
            {
                "id": "m1",
                "date": "2026-02-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "m2",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "m3",
                "date": "2026-03-10",
                "merchant": "Movies",
                "category": "entertainment",
                "amount": 240.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )

    result = run_langgraph_chat(session_id=session_id, question="how can i save 200 this month?")
    assert result["status"] == "done"
    assert "plan_savings" in result["tool_calls"]
    assert "Suggested cuts:" in result["answer"]
