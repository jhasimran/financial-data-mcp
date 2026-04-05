from __future__ import annotations

from typing import Any, Literal, TypedDict


class PlannedToolCall(TypedDict):
    name: str
    args: dict[str, Any]


class AgentState(TypedDict):
    session_id: str
    user_message: str
    status: Literal["running", "error", "needs_input", "done"]
    missing_input: str | None
    error_message: str
    error_messages: list[str]
    attachments_present: bool
    attachment_paths: list[str]
    parsed_transactions: list[dict[str, Any]]
    tool_plan: list[PlannedToolCall]
    next_step: int
    tool_calls: list[str]
    tool_outputs: dict[str, Any]
    warnings: list[str]
    answer: str
    has_transaction_data: bool
