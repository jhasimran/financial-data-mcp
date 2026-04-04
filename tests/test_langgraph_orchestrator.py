from __future__ import annotations

import re

from app.agent.run import run_langgraph_chat
from app.tools.common import TRANSACTION_STORE
from app.tools.transactions import set_ingested_transactions


def _create_session() -> str:
    return TRANSACTION_STORE.create_session()


def test_langgraph_requires_ingestion_for_transaction_queries() -> None:
    session_id = _create_session()
    result = run_langgraph_chat(session_id=session_id, question="show my spending summary")
    assert result["status"] == "needs_ingestion"
    assert "Upload PDFs first" in result["answer"]


def test_langgraph_allows_market_queries_without_ingestion(monkeypatch) -> None:
    session_id = _create_session()

    def fake_execute_tool(name: str, args: dict, session_id: str) -> dict:
        assert name == "get_crypto_price"
        return {
            "asset": "bitcoin",
            "vs_currency": "usd",
            "price": 12345.67,
            "source": "coingecko.com",
            "cache_hit": True,
        }

    monkeypatch.setattr("app.agent.nodes.execute_tool", fake_execute_tool)
    result = run_langgraph_chat(session_id=session_id, question="what is bitcoin price now?")
    assert result["status"] == "done"
    assert "get_crypto_price" in result["tool_calls"]
    assert result["answer"]


def test_langgraph_redacts_sensitive_tokens_in_supporting_data() -> None:
    session_id = _create_session()
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


def test_langgraph_session_isolation() -> None:
    session_with_data = _create_session()
    session_without_data = _create_session()
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
    assert empty_result["status"] == "needs_ingestion"


def test_langgraph_routes_savings_target_queries_to_budget_planner() -> None:
    session_id = _create_session()
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


def test_langgraph_routes_max_savings_queries_to_budget_planner() -> None:
    session_id = _create_session()
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
        question="What is the max savings I can do this month?",
    )
    assert result["status"] == "done"
    assert "plan_savings" in result["tool_calls"]
    assert result["answer"]


def test_langgraph_capability_query_returns_help_without_tools(monkeypatch) -> None:
    session_id = _create_session()
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)

    result = run_langgraph_chat(session_id=session_id, question="what can you do for me?")
    assert result["status"] == "done"
    assert result["tool_calls"] == []
    assert "ingest PDF statements" in result["answer"]


def test_langgraph_spending_categories_answer_includes_category_names(monkeypatch) -> None:
    session_id = _create_session()
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
    session_id = _create_session()
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
