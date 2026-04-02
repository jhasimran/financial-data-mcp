"""Reserved for future stock tools (Alpha Vantage, etc.)."""


def not_implemented_stock_tool() -> dict:
    return {
        "status": "not_implemented",
        "message": "Stock tooling is intentionally deferred beyond V1.",
    }
