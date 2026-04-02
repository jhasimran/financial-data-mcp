import pytest

from app.tools.transactions import (
    flag_transaction_anomalies,
    list_seed_transactions,
    spending_summary,
)


def test_list_transactions_has_data() -> None:
    result = list_seed_transactions(limit=5)
    assert result["count"] == 5
    assert result["total_available"] >= 20
    assert len(result["transactions"]) == 5


def test_spending_summary_by_period() -> None:
    result = spending_summary(start_date="2026-03-01", end_date="2026-03-31")
    assert result["currency"] == "USD"
    assert result["total_spend"] > 0
    assert "food" in result["totals_by_category"]
    assert result["transaction_count"] > 0


def test_anomaly_detection_with_min_amount() -> None:
    result = flag_transaction_anomalies(min_amount=1000.0)
    assert result["count"] >= 1
    for item in result["anomalies"]:
        assert item["amount"] >= 1000.0


def test_anomaly_detection_flags_unusually_low_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_expenses = [
        {"id": "t1", "date": "2026-03-01", "merchant": "A", "category": "food", "amount": 100.0, "currency": "USD", "direction": "debit"},
        {"id": "t2", "date": "2026-03-02", "merchant": "B", "category": "food", "amount": 100.0, "currency": "USD", "direction": "debit"},
        {"id": "t3", "date": "2026-03-03", "merchant": "C", "category": "food", "amount": 101.0, "currency": "USD", "direction": "debit"},
        {"id": "t4", "date": "2026-03-04", "merchant": "D", "category": "food", "amount": 102.0, "currency": "USD", "direction": "debit"},
        {"id": "t5", "date": "2026-03-05", "merchant": "E", "category": "food", "amount": 40.0, "currency": "USD", "direction": "debit"},
    ]
    monkeypatch.setattr(
        "app.tools.transactions._filter_transactions",
        lambda **_: mock_expenses,
    )

    result = flag_transaction_anomalies()

    assert result["count"] == 1
    assert result["anomalies"][0]["id"] == "t5"
    assert result["anomalies"][0]["reason"].startswith("robust_z_score=-")


def test_transactions_validation_error() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        list_seed_transactions(start_date="03-01-2026")
