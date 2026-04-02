from __future__ import annotations


class ExternalAPIError(RuntimeError):
    """Raised when an upstream public API fails."""
