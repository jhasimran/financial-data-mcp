from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.tools.common import TRANSACTION_STORE
from app.tools.transactions import set_ingested_transactions


client = TestClient(app)


def test_create_session_and_status() -> None:
    response = client.post("/api/session")
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    status = client.get(f"/api/session/{session_id}/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["session_id"] == session_id
    assert payload["has_data"] is False


def test_chat_requires_ingestion() -> None:
    session_id = client.post("/api/session").json()["session_id"]
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "question": "summarize spending"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"].startswith("No ingested transactions")


def test_chat_returns_answer_after_ingestion() -> None:
    session_id = client.post("/api/session").json()["session_id"]
    set_ingested_transactions(
        [
            {
                "id": "t1",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            }
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "question": "show summary"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert "get_spending_summary" in payload["tool_calls"]


def test_chat_returns_budget_plan_after_ingestion() -> None:
    session_id = client.post("/api/session").json()["session_id"]
    set_ingested_transactions(
        [
            {
                "id": "t1",
                "date": "2026-02-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "t2",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "t3",
                "date": "2026-03-09",
                "merchant": "Movies",
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
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "question": "How can I save 200 this month?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "plan_savings" in payload["tool_calls"]
    assert "plan_savings" in payload["supporting_data"]
    assert payload["answer"]


def test_chat_capability_query_returns_help_text(monkeypatch) -> None:
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    session_id = client.post("/api/session").json()["session_id"]
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "question": "what can you do for me?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"] == []
    assert "ingest PDF statements" in payload["answer"]


def test_chat_spending_categories_answer_includes_category_name(monkeypatch) -> None:
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    session_id = client.post("/api/session").json()["session_id"]
    set_ingested_transactions(
        [
            {
                "id": "t1",
                "date": "2026-02-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "t2",
                "date": "2026-02-05",
                "merchant": "Fresh Mart",
                "category": "food",
                "amount": 300.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
        session_id=session_id,
    )
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "question": "what are my top spending categories?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "get_spending_summary" in payload["tool_calls"]
    assert "rent" in payload["answer"].lower() or "food" in payload["answer"].lower()


def test_ingest_endpoint(monkeypatch, tmp_path: Path) -> None:
    session_id = client.post("/api/session").json()["session_id"]

    def fake_ingest(file_paths: list[str]) -> dict:
        assert len(file_paths) == 1
        return {
            "transactions": [
                {
                    "id": "i1",
                    "date": "2026-03-21",
                    "merchant": "Cafe",
                    "category": "food",
                    "amount": 5.6,
                    "currency": "USD",
                    "direction": "debit",
                }
            ],
            "count": 1,
            "sources": 1,
            "warnings": [],
        }

    monkeypatch.setattr("app.api.orchestrator.ingest_financial_documents", fake_ingest)

    sample = tmp_path / "statement.pdf"
    sample.write_bytes(b"pdf")
    with sample.open("rb") as handle:
        response = client.post(
            f"/api/documents/ingest?session_id={session_id}",
            files={"files": ("statement.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert TRANSACTION_STORE.has_data(session_id) is True
