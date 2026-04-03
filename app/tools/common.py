from __future__ import annotations

import logging
import time
from copy import deepcopy
from uuid import uuid4

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
    """Process-local store for sanitized ingested transactions per session."""

    def __init__(self) -> None:
        self._transactions: dict[str, list[dict]] = {}
        self._metadata: dict[str, dict] = {}

    def create_session(self) -> str:
        session_id = str(uuid4())
        self._transactions[session_id] = []
        self._metadata[session_id] = {"sources": 0, "warnings": []}
        return session_id

    def has_session(self, session_id: str) -> bool:
        return session_id in self._transactions

    def has_data(self, session_id: str) -> bool:
        return len(self._transactions.get(session_id, [])) > 0

    def set(
        self, session_id: str, transactions: list[dict], sources: int, warnings: list[str]
    ) -> None:
        if not self.has_session(session_id):
            self.create_with_id(session_id)
        self._transactions[session_id] = deepcopy(transactions)
        self._metadata[session_id] = {"sources": sources, "warnings": list(warnings)}

    def create_with_id(self, session_id: str) -> None:
        self._transactions[session_id] = []
        self._metadata[session_id] = {"sources": 0, "warnings": []}

    def get_transactions(self, session_id: str) -> list[dict]:
        return deepcopy(self._transactions.get(session_id, []))

    def get_metadata(self, session_id: str) -> dict:
        return deepcopy(self._metadata.get(session_id, {"sources": 0, "warnings": []}))

    def clear(self, session_id: str) -> None:
        self._transactions[session_id] = []
        self._metadata[session_id] = {"sources": 0, "warnings": []}


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
