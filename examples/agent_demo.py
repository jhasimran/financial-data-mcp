from __future__ import annotations

from pprint import pprint

from app.tools.insights import financial_insights
from app.tools.transactions import set_ingested_transactions


def main() -> None:
    # Simulate a privacy-safe ingestion step (sanitized transactions only).
    set_ingested_transactions(
        transactions=[
            {
                "id": "demo_1",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "demo_2",
                "date": "2026-03-10",
                "merchant": "Cafe Brew",
                "category": "food",
                "amount": 12.4,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "demo_3",
                "date": "2026-03-19",
                "merchant": "Airline Co",
                "category": "travel",
                "amount": 1280.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        sources=1,
        warnings=[],
    )

    # Simulate an agent choosing one high-level analytics call.
    result = financial_insights(
        start_date="2026-03-01",
        end_date="2026-03-31",
        min_amount=50.0,
    )

    # Render a concise, readable terminal summary for humans.
    print("=== Financial Insights Demo ===")
    print(f"Period: {result['period']}")
    print("\nSummary:")
    pprint(result["summary"])
    print("\nAnomalies:")
    pprint(result["anomalies"])
    print("\nInsights:")
    for idx, line in enumerate(result["insights"], start=1):
        print(f"{idx}. {line}")
    if result["errors"]:
        print("\nErrors:")
        pprint(result["errors"])


if __name__ == "__main__":
    main()
