from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.tools.common import TRANSACTION_STORE
from app.tools.transactions import set_ingested_transactions
from tests.helpers import fake_ingest_result


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


def test_chat_without_transactions_returns_needs_input() -> None:
    session_id = client.post("/api/session").json()["session_id"]
    response = client.post(
        "/api/chat",
        data={"session_id": session_id, "question": "summarize spending"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "needs_input"
    assert response.json()["missing_input"] == "transactions"


def test_chat_returns_answer_after_existing_ingestion(monkeypatch) -> None:
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
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
        data={"session_id": session_id, "question": "show summary"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["answer"]
    assert "get_spending_summary" in payload["tool_calls"]


def test_chat_accepts_question_and_files_in_one_request(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.agent.nodes._anthropic_chat", lambda *_: None)
    monkeypatch.setattr("app.agent.nodes.ingest_financial_documents", lambda **_: fake_ingest_result())
    session_id = client.post("/api/session").json()["session_id"]

    sample = tmp_path / "statement.pdf"
    sample.write_bytes(b"pdf")
    with sample.open("rb") as handle:
        response = client.post(
            "/api/chat",
            data={"session_id": session_id, "question": "show summary"},
            files=[("files", ("statement.pdf", handle, "application/pdf"))],
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert "get_spending_summary" in payload["tool_calls"]
    assert TRANSACTION_STORE.has_data(session_id) is True


def test_chat_with_files_only_returns_follow_up_prompt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.agent.nodes.ingest_financial_documents", lambda **_: fake_ingest_result())
    session_id = client.post("/api/session").json()["session_id"]

    sample = tmp_path / "statement.pdf"
    sample.write_bytes(b"pdf")
    with sample.open("rb") as handle:
        response = client.post(
            "/api/chat",
            data={"session_id": session_id, "question": ""},
            files=[("files", ("statement.pdf", handle, "application/pdf"))],
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_input"
    assert payload["missing_input"] == "question"
    assert "analyze next" in payload["answer"].lower()


def test_chat_runs_multi_tool_plan_after_ingestion(monkeypatch) -> None:
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
        data={"session_id": session_id, "question": "Summarize my spending and flag unusual transactions"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert "get_spending_summary" in payload["tool_calls"]
    assert "flag_anomalies" in payload["tool_calls"]
    assert payload["answer"]
