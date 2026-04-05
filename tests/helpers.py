from __future__ import annotations

from app.tools.common import TRANSACTION_STORE


def create_session() -> str:
    return TRANSACTION_STORE.create_session()


def fake_ingest_result() -> dict:
    return {
        "transactions": [
            {
                "id": "ingested_1",
                "date": "2026-03-01",
                "merchant": "Landlord LLC",
                "category": "rent",
                "amount": 1600.0,
                "currency": "USD",
                "direction": "debit",
            },
            {
                "id": "ingested_2",
                "date": "2026-03-05",
                "merchant": "Fresh Mart",
                "category": "food",
                "amount": 320.0,
                "currency": "USD",
                "direction": "debit",
            },
        ],
        "count": 2,
        "sources": 1,
        "warnings": [],
    }


def planner_sample_transactions() -> list[dict]:
    return [
        {
            "id": "m1_rent",
            "date": "2026-02-01",
            "merchant": "Landlord LLC",
            "category": "rent",
            "amount": 1600.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m1_food",
            "date": "2026-02-05",
            "merchant": "Fresh Mart",
            "category": "food",
            "amount": 320.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m1_ent",
            "date": "2026-02-10",
            "merchant": "Movies",
            "category": "entertainment",
            "amount": 180.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m2_rent",
            "date": "2026-03-01",
            "merchant": "Landlord LLC",
            "category": "rent",
            "amount": 1600.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m2_food",
            "date": "2026-03-05",
            "merchant": "Fresh Mart",
            "category": "food",
            "amount": 280.0,
            "currency": "USD",
            "direction": "debit",
        },
        {
            "id": "m2_ent",
            "date": "2026-03-12",
            "merchant": "Concerts",
            "category": "entertainment",
            "amount": 220.0,
            "currency": "USD",
            "direction": "debit",
        },
    ]
