from __future__ import annotations

from pprint import pprint

from app.tools.insights import financial_insights


def main() -> None:
    # Simulate an agent choosing one high-level tool call.
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
