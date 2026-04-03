from __future__ import annotations

from app.tools.common import ExternalAPIError, IngestionRequiredError, get_logger
from app.tools.transactions import flag_transaction_anomalies, spending_summary

logger = get_logger(__name__)


def _compute_insights(summary: dict | None, anomalies: dict | None) -> list[str]:
    insights: list[str] = []

    if summary:
        total_spend = float(summary.get("total_spend", 0.0))
        rent_spend = float(summary.get("totals_by_category", {}).get("rent", 0.0))
        if total_spend > 0:
            rent_ratio = rent_spend / total_spend
            if rent_ratio >= 0.35:
                insights.append(
                    f"Rent is {rent_ratio:.0%} of total spend, which may pressure monthly cash flow."
                )

    if anomalies:
        anomaly_count = int(anomalies.get("count", 0))
        if anomaly_count > 0:
            insights.append(
                f"{anomaly_count} unusual transaction(s) detected. Review spikes for one-off or avoidable spend."
            )

    if not insights:
        insights.append("No major spending risk signals detected for this period.")
    return insights


def financial_insights(
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
) -> dict:
    errors: list[dict] = []
    summary: dict | None = None
    anomalies: dict | None = None

    try:
        summary = spending_summary(start_date=start_date, end_date=end_date)
    except IngestionRequiredError:
        logger.warning("Insights summary requires ingestion.")
        errors.append(
            {
                "component": "summary",
                "error": "No ingested transactions available. Run ingest_financial_documents first.",
                "source": "ingestion",
            }
        )
    except (ValueError, ExternalAPIError) as exc:
        logger.exception("Failed to compute spending summary")
        source = getattr(exc, "source", "transactions")
        errors.append(
            {
                "component": "summary",
                "error": "Unable to compute spending summary.",
                "source": source,
            }
        )

    try:
        anomalies = flag_transaction_anomalies(
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount,
        )
    except IngestionRequiredError:
        logger.warning("Insights anomaly detection requires ingestion.")
        errors.append(
            {
                "component": "anomalies",
                "error": "No ingested transactions available. Run ingest_financial_documents first.",
                "source": "ingestion",
            }
        )
    except (ValueError, ExternalAPIError) as exc:
        logger.exception("Failed to compute anomalies")
        source = getattr(exc, "source", "transactions")
        errors.append(
            {
                "component": "anomalies",
                "error": "Unable to compute anomalies.",
                "source": source,
            }
        )

    return {
        "ok": len(errors) == 0,
        "period": {"start_date": start_date, "end_date": end_date},
        "summary": summary,
        "anomalies": anomalies,
        "insights": _compute_insights(summary=summary, anomalies=anomalies),
        "errors": errors,
    }
