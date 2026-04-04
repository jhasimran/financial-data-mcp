from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.tools.common import IngestionRequiredError, TRANSACTION_STORE

STRATEGY_FACTORS = {
    "conservative": 0.7,
    "balanced": 1.0,
    "aggressive": 1.25,
}

CATEGORY_CUT_CAPS = {
    "rent": 0.03,
    "utilities": 0.08,
    "health": 0.08,
    "education": 0.10,
    "transport": 0.15,
    "food": 0.25,
    "entertainment": 0.50,
    "travel": 0.45,
    "other": 0.30,
}

FIXED_CATEGORIES = {"rent", "utilities"}


def _monthly_category_totals(records: list[dict]) -> tuple[dict[str, float], int]:
    by_month_category: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for tx in records:
        if tx.get("direction") != "debit":
            continue
        raw_date = tx.get("date")
        if not isinstance(raw_date, str):
            continue
        try:
            tx_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        month_key = tx_date.strftime("%Y-%m")
        category = str(tx.get("category", "other")).lower()
        amount = float(tx.get("amount", 0.0))
        by_month_category[month_key][category] += amount

    month_count = len(by_month_category)
    if month_count == 0:
        return {}, 0

    totals_by_category: dict[str, float] = defaultdict(float)
    for month_payload in by_month_category.values():
        for category, amount in month_payload.items():
            totals_by_category[category] += amount

    averages = {
        category: round(total / month_count, 2)
        for category, total in totals_by_category.items()
    }
    return averages, month_count


def plan_savings(
    *,
    session_id: str,
    target_amount: float | None = None,
    strategy: str = "balanced",
) -> dict:
    if target_amount is not None and target_amount < 0:
        raise ValueError("target_amount must be non-negative when provided.")

    strategy_key = strategy.strip().lower()
    if strategy_key not in STRATEGY_FACTORS:
        raise ValueError("strategy must be one of: conservative, balanced, aggressive.")

    records = TRANSACTION_STORE.get_transactions(session_id=session_id)
    if not records:
        raise IngestionRequiredError(
            "No ingested transactions found. Call ingest_financial_documents first."
        )

    avg_monthly_by_category, months_of_history = _monthly_category_totals(records)
    if not avg_monthly_by_category:
        raise ValueError("No debit transactions available for budget planning.")

    factor = STRATEGY_FACTORS[strategy_key]
    recommendations: list[dict] = []
    max_savings = 0.0
    for category, baseline in sorted(
        avg_monthly_by_category.items(), key=lambda item: item[1], reverse=True
    ):
        cut_cap = CATEGORY_CUT_CAPS.get(category, CATEGORY_CUT_CAPS["other"])
        potential_cut = round(baseline * min(cut_cap * factor, 0.9), 2)
        if potential_cut <= 0:
            continue
        max_savings += potential_cut
        recommendations.append(
            {
                "category": category,
                "baseline_monthly_spend": round(baseline, 2),
                "suggested_cut": potential_cut,
                "is_fixed": category in FIXED_CATEGORIES,
                "action_hint": (
                    "Monitor usage and optimize providers."
                    if category in FIXED_CATEGORIES
                    else "Reduce discretionary spend gradually."
                ),
            }
        )

    max_savings = round(max_savings, 2)
    target = round(float(target_amount), 2) if target_amount is not None else None
    target_met = target is None or max_savings >= target
    projected_spend = round(sum(avg_monthly_by_category.values()) - max_savings, 2)

    warnings: list[str] = []
    if months_of_history < 2:
        warnings.append(
            "Savings estimates are based on limited history; upload more months for higher confidence."
        )

    return {
        "strategy": strategy_key,
        "months_of_history": months_of_history,
        "target_amount": target,
        "target_met": target_met,
        "baseline_monthly_spend": round(sum(avg_monthly_by_category.values()), 2),
        "projected_monthly_spend": projected_spend,
        "max_savings_estimate": max_savings,
        "category_baseline": dict(sorted(avg_monthly_by_category.items())),
        "recommendations": recommendations,
        "assumptions": [
            "Plan uses monthly category averages from ingested debit transactions.",
            "Suggested cuts are capped by category-specific reduction ceilings.",
            "Fixed categories are treated as harder-to-reduce expenses.",
        ],
        "warnings": warnings,
    }
