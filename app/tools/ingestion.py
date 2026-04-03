from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from app.tools.common import get_logger

logger = get_logger(__name__)

LINE_PATTERN = re.compile(
    r"(?P<date>\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(?P<merchant>.+?)\s+(?P<amount>-?\$?\d+(?:,\d{3})*(?:\.\d{2})?)$"
)
EMAIL_PATTERN = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{6,}\b")
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.\- ]+\s(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Blvd|Lane|Ln)\b",
    flags=re.IGNORECASE,
)
WHITESPACE_PATTERN = re.compile(r"\s+")


def _normalize_date(value: str) -> str:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d", "%m-%d-%Y", "%m-%d-%y", "%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt in ("%m/%d", "%m-%d"):
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.date().isoformat()
        except ValueError:
            continue
    raise ValueError("Unsupported transaction date format encountered during ingestion.")


def _sanitize_merchant(raw_merchant: str) -> str:
    candidate = EMAIL_PATTERN.sub("[redacted-email]", raw_merchant)
    candidate = LONG_NUMBER_PATTERN.sub("[redacted-number]", candidate)
    candidate = ADDRESS_PATTERN.sub("[redacted-address]", candidate)
    candidate = WHITESPACE_PATTERN.sub(" ", candidate).strip()
    if not candidate:
        return "Unknown Merchant"
    return candidate[:120]


def _normalize_amount(value: str) -> tuple[float, str]:
    cleaned = value.replace("$", "").replace(",", "").strip()
    amount = float(cleaned)
    if amount < 0:
        return abs(amount), "debit"
    return amount, "credit"


def _guess_category(merchant: str) -> str:
    text = merchant.lower()
    if any(k in text for k in ("rent", "landlord", "property")):
        return "rent"
    if any(k in text for k in ("cafe", "coffee", "restaurant", "mart", "grocery")):
        return "food"
    if any(k in text for k in ("uber", "lyft", "metro", "fuel", "gas")):
        return "transport"
    if any(k in text for k in ("pharma", "clinic", "health", "hospital")):
        return "health"
    if any(k in text for k in ("airline", "hotel", "travel")):
        return "travel"
    if any(k in text for k in ("electric", "water", "utility", "power")):
        return "utilities"
    return "other"


def _extract_transactions_from_text(text: str, source_label: str) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    transactions: list[dict] = []
    for line in text.splitlines():
        matched = LINE_PATTERN.search(line.strip())
        if not matched:
            continue
        try:
            date_iso = _normalize_date(matched.group("date"))
            amount, direction = _normalize_amount(matched.group("amount"))
            merchant = _sanitize_merchant(matched.group("merchant"))
            idx = len(transactions) + 1
            transactions.append(
                {
                    "id": f"ingested_{source_label}_{idx}",
                    "date": date_iso,
                    "merchant": merchant,
                    "category": _guess_category(merchant),
                    "amount": round(amount, 2),
                    "currency": "USD",
                    "direction": direction,
                }
            )
        except ValueError:
            warnings.append("Some lines were skipped due to unsupported date/amount formats.")
    return transactions, warnings


def ingest_financial_documents(file_paths: list[str]) -> dict:
    if not file_paths:
        raise ValueError("file_paths must contain at least one PDF file path.")

    all_transactions: list[dict] = []
    warnings: list[str] = []

    for index, path in enumerate(file_paths, start=1):
        file_path = Path(path)
        if file_path.suffix.lower() != ".pdf":
            warnings.append(f"Skipped non-PDF input at position {index}.")
            continue
        if not file_path.exists():
            warnings.append(f"Skipped unreadable file at position {index}.")
            continue

        logger.info("Processing financial document #%s", index)
        try:
            with pdfplumber.open(file_path) as pdf:
                pages_text = [page.extract_text() or "" for page in pdf.pages]
        except Exception:
            warnings.append(f"Failed to parse document at position {index}.")
            continue

        source_tx, source_warnings = _extract_transactions_from_text(
            "\n".join(pages_text), f"doc{index}"
        )
        all_transactions.extend(source_tx)
        warnings.extend(source_warnings)

    deduped_warnings = list(dict.fromkeys(warnings))
    return {
        "transactions": all_transactions,
        "count": len(all_transactions),
        "sources": len(file_paths),
        "warnings": deduped_warnings,
    }
