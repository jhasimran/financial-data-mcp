from __future__ import annotations

import re
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{6,}\b")
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.\- ]+\s(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Blvd|Lane|Ln)\b",
    flags=re.IGNORECASE,
)


def redact_text(text: str) -> str:
    value = EMAIL_PATTERN.sub("[redacted-email]", text)
    value = LONG_NUMBER_PATTERN.sub("[redacted-number]", value)
    value = ADDRESS_PATTERN.sub("[redacted-address]", value)
    return value


def sanitize_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [sanitize_data(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_data(item) for key, item in value.items()}
    return value
