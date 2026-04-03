import pytest

from app.tools.common import IngestionRequiredError
from app.tools.transactions import (
    clear_ingested_transactions,
    flag_transaction_anomalies,
    list_seed_transactions,
    set_ingested_transactions,
    spending_summary,
)


@pytest.fixture(autouse=True)
def _cleanup_store() -> None:
    clear_ingested_transactions()
    yield
    clear_ingested_transactions()


def _sample_transactions() -> list[dict]:
    return [
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
            "amount": 80.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "tx_3",
            "date": "2026-03-03",
            "merchant": "Cafe Brew",
            "category": "food",
            "amount": 65.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "tx_4",
            "date": "2026-03-04",
            "merchant": "Fuel Station",
            "category": "transport",
            "amount": 55.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "tx_5",
            "date": "2026-03-05",
            "merchant": "Employer Inc",
            "category": "salary",
            "amount": 4000.0,
            "currency": "USD",
            "direction": "credit",
        },
    ]


def test_transactions_require_ingestion() -> None:
    with pytest.raises(IngestionRequiredError, match="ingest_financial_documents"):
        list_seed_transactions()


def test_list_transactions_has_data() -> None:
    set_ingested_transactions(_sample_transactions(), sources=1, warnings=[])
    result = list_seed_transactions(limit=5)
    assert result["count"] == 5
    assert result["total_available"] == 5
    assert len(result["transactions"]) == 5


def test_spending_summary_by_period() -> None:
    set_ingested_transactions(_sample_transactions(), sources=1, warnings=[])
    result = spending_summary(start_date="2026-03-01", end_date="2026-03-31")
    assert result["currency"] == "USD"
    assert result["total_spend"] > 0
    assert "food" in result["totals_by_category"]
    assert result["transaction_count"] > 0


def test_anomaly_detection_with_min_amount() -> None:
    set_ingested_transactions(_sample_transactions(), sources=1, warnings=[])
    result = flag_transaction_anomalies(min_amount=1000.0)
    assert result["count"] >= 1
    for item in result["anomalies"]:
        assert item["amount"] >= 1000.0


def test_anomaly_detection_flags_unusually_low_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_ingested_transactions(_sample_transactions(), sources=1, warnings=[])
    mock_transactions = [
        {"id": "t1", "date": "2026-03-01", "merchant": "A", "category": "food", "amount": 100.0, "currency": "USD", "direction": "debit"},
        {"id": "t2", "date": "2026-03-02", "merchant": "B", "category": "food", "amount": 100.0, "currency": "USD", "direction": "debit"},
        {"id": "t3", "date": "2026-03-03", "merchant": "C", "category": "food", "amount": 101.0, "currency": "USD", "direction": "debit"},
        {"id": "t4", "date": "2026-03-04", "merchant": "D", "category": "food", "amount": 102.0, "currency": "USD", "direction": "debit"},
        {"id": "t5", "date": "2026-03-05", "merchant": "E", "category": "food", "amount": 40.0, "currency": "USD", "direction": "debit"},
    ]
    monkeypatch.setattr(
        "app.tools.transactions._filter_transactions",
        lambda **_: mock_transactions,
    )

    result = flag_transaction_anomalies()

    assert result["count"] == 1
    assert result["anomalies"][0]["id"] == "t5"
    assert result["anomalies"][0]["reason"].startswith("robust_z_score=-")


def test_transactions_validation_error() -> None:
    set_ingested_transactions(_sample_transactions(), sources=1, warnings=[])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        list_seed_transactions(start_date="03-01-2026")
