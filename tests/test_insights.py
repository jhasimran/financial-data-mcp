import pytest

from app.tools.insights import financial_insights
from app.tools.transactions import clear_ingested_transactions, set_ingested_transactions


def test_financial_insights_happy_path() -> None:
    clear_ingested_transactions()
    set_ingested_transactions(
        [
            {
                "id": "tx_1",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "tx_2",
                "date": "2026-03-02",
                "merchant": "Fresh Mart",
                "category": "food",
                "amount": 75.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
    )
    result = financial_insights(start_date="2026-03-01", end_date="2026-03-31")
    assert result["summary"] is not None
    assert result["anomalies"] is not None
    assert isinstance(result["insights"], list)
    assert result["errors"] == []
    assert result["ok"] is True


def test_financial_insights_high_rent_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.tools.insights.spending_summary",
        lambda **_: {
            "total_spend": 2000.0,
            "totals_by_category": {"rent": 900.0},
        },
    )
    monkeypatch.setattr(
        "app.tools.insights.flag_transaction_anomalies",
        lambda **_: {"count": 0, "anomalies": []},
    )
    result = financial_insights()
    assert any("Rent is" in line for line in result["insights"])


def test_financial_insights_unusual_spikes_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.tools.insights.spending_summary",
        lambda **_: {"total_spend": 1000.0, "totals_by_category": {"food": 100.0}},
    )
    monkeypatch.setattr(
        "app.tools.insights.flag_transaction_anomalies",
        lambda **_: {"count": 2, "anomalies": [{"id": "a1"}, {"id": "a2"}]},
    )
    result = financial_insights()
    assert any("unusual transaction" in line for line in result["insights"])


def test_financial_insights_partial_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_summary(**_) -> dict:
        raise ValueError("bad date")

    monkeypatch.setattr("app.tools.insights.spending_summary", fail_summary)
    monkeypatch.setattr(
        "app.tools.insights.flag_transaction_anomalies",
        lambda **_: {"count": 0, "anomalies": []},
    )
    result = financial_insights()
    assert result["summary"] is None
    assert result["anomalies"] is not None
    assert result["ok"] is False
    assert result["errors"][0]["component"] == "summary"


def test_financial_insights_requires_ingestion() -> None:
    clear_ingested_transactions()
    result = financial_insights()
    assert result["ok"] is False
    assert result["summary"] is None
    assert result["anomalies"] is None
    assert len(result["errors"]) == 2
    assert all(item["source"] == "ingestion" for item in result["errors"])
