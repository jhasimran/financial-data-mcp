from __future__ import annotations

from typing import Any, Literal, TypedDict


class PlannedToolCall(TypedDict):
    name: str
    args: dict[str, Any]


class AgentState(TypedDict):
    session_id: str
    user_question: str
    status: Literal["running", "error", "needs_ingestion", "done"]
    error_message: str
    plan: list[PlannedToolCall]
    next_step: int
    tool_calls: list[str]
    supporting_data: dict[str, Any]
    warnings: list[str]
    answer: str
    has_transaction_data: bool
