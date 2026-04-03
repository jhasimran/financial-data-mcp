from __future__ import annotations

from datetime import date
from statistics import median

from app.tools.common import IngestionRequiredError, TRANSACTION_STORE


def _parse_iso_date(raw_date: str, field_name: str) -> date:
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD.") from exc


def set_ingested_transactions(
    transactions: list[dict], sources: int, warnings: list[str], session_id: str = "default"
) -> None:
    TRANSACTION_STORE.set(
        session_id=session_id,
        transactions=transactions,
        sources=sources,
        warnings=warnings,
    )


def clear_ingested_transactions(session_id: str = "default") -> None:
    TRANSACTION_STORE.clear(session_id=session_id)


def _load_transactions(session_id: str = "default") -> list[dict]:
    records = TRANSACTION_STORE.get_transactions(session_id=session_id)
    if not records:
        raise IngestionRequiredError(
            "No ingested transactions found. Call ingest_financial_documents first."
        )
    return records


def _filter_transactions(
    *,
    start_date: str | None,
    end_date: str | None,
    category: str | None = None,
    session_id: str = "default",
) -> list[dict]:
    records = _load_transactions(session_id=session_id)
    start = _parse_iso_date(start_date, "start_date") if start_date else None
    end = _parse_iso_date(end_date, "end_date") if end_date else None
    wanted_category = category.lower().strip() if category else None

    filtered: list[dict] = []
    for record in records:
        tx_date = _parse_iso_date(record["date"], "transaction date")
        if start and tx_date < start:
            continue
        if end and tx_date > end:
            continue
        if wanted_category and record["category"].lower() != wanted_category:
            continue
        filtered.append(record)

    filtered.sort(key=lambda tx: tx["date"], reverse=True)
    return filtered


def list_seed_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    limit: int = 50,
    session_id: str = "default",
) -> dict:
    if limit <= 0:
        raise ValueError("limit must be greater than 0.")

    transactions = _filter_transactions(
        start_date=start_date,
        end_date=end_date,
        category=category,
        session_id=session_id,
    )
    sliced = transactions[:limit]

    return {
        "count": len(sliced),
        "total_available": len(transactions),
        "transactions": sliced,
    }


def spending_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    session_id: str = "default",
) -> dict:
    transactions = _filter_transactions(
        start_date=start_date,
        end_date=end_date,
        category=None,
        session_id=session_id,
    )
    expenses = [tx for tx in transactions if tx.get("direction") == "debit"]

    totals_by_category: dict[str, float] = {}
    for tx in expenses:
        category = tx["category"]
        totals_by_category[category] = round(
            totals_by_category.get(category, 0.0) + float(tx["amount"]),
            2,
        )

    total_spend = round(sum(float(tx["amount"]) for tx in expenses), 2)

    return {
        "period": {"start_date": start_date, "end_date": end_date},
        "total_spend": total_spend,
        "transaction_count": len(expenses),
        "totals_by_category": dict(sorted(totals_by_category.items())),
        "currency": "USD",
    }


def flag_transaction_anomalies(
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    session_id: str = "default",
) -> dict:
    if min_amount is not None and min_amount < 0:
        raise ValueError("min_amount must be non-negative when provided.")

    transactions = _filter_transactions(
        start_date=start_date,
        end_date=end_date,
        category=None,
        session_id=session_id,
    )
    expenses = [tx for tx in transactions if tx.get("direction") == "debit"]
    amounts = [float(tx["amount"]) for tx in expenses]

    if not expenses:
        return {"count": 0, "anomalies": []}

    center = median(amounts)
    deviations = [abs(amount - center) for amount in amounts]
    mad = median(deviations)

    anomalies: list[dict] = []
    for tx in expenses:
        amount = float(tx["amount"])
        if min_amount is not None and amount < min_amount:
            continue

        if mad > 0:
            robust_z = 0.6745 * (amount - center) / mad
            is_anomaly = abs(robust_z) > 3.5
            reason = f"robust_z_score={round(robust_z, 2)}"
        else:
            threshold = center * 2.5
            is_anomaly = amount > threshold
            reason = f"amount_exceeds_{round(threshold, 2)}"

        if is_anomaly:
            anomalies.append(
                {
                    "id": tx["id"],
                    "date": tx["date"],
                    "merchant": tx["merchant"],
                    "category": tx["category"],
                    "amount": amount,
                    "currency": tx["currency"],
                    "reason": reason,
                }
            )

    return {
        "count": len(anomalies),
        "baseline": {"median": round(center, 2), "mad": round(mad, 2)},
        "anomalies": anomalies,
    }
