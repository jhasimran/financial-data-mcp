from __future__ import annotations

import logging
import time
from copy import deepcopy

class ExternalAPIError(RuntimeError):
    """Raised when an upstream public API fails."""

    def __init__(self, message: str, source: str = "external_api"):
        super().__init__(message)
        self.source = source


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    return logger


def error_payload(error: str, source: str, error_type: str = "tool_error") -> dict:
    return {
        "ok": False,
        "error": error,
        "source": source,
        "type": error_type,
    }


class IngestionRequiredError(ValueError):
    """Raised when transaction tools are used before document ingestion."""


class InMemoryTransactionStore:
    """Process-local store for sanitized ingested transactions."""

    def __init__(self) -> None:
        self._transactions: list[dict] = []
        self._metadata: dict = {"sources": 0, "warnings": []}

    def has_data(self) -> bool:
        return len(self._transactions) > 0

    def set(self, transactions: list[dict], sources: int, warnings: list[str]) -> None:
        self._transactions = deepcopy(transactions)
        self._metadata = {"sources": sources, "warnings": list(warnings)}

    def get_transactions(self) -> list[dict]:
        return deepcopy(self._transactions)

    def get_metadata(self) -> dict:
        return deepcopy(self._metadata)

    def clear(self) -> None:
        self._transactions = []
        self._metadata = {"sources": 0, "warnings": []}


TRANSACTION_STORE = InMemoryTransactionStore()


class TTLCache:
    """Small in-memory TTL cache for public API calls."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, dict]] = {}

    def get(self, key: str) -> dict | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.time() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: dict) -> None:
        self._store[key] = (time.time() + self.ttl_seconds, value)
