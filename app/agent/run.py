from __future__ import annotations

from app.agent.graph import build_agent_graph
from app.agent.state import AgentState

GRAPH = build_agent_graph()


def run_langgraph_chat(
    session_id: str,
    question: str | None = None,
    attachment_paths: list[str] | None = None,
) -> dict:
    initial_state: AgentState = {
        "session_id": session_id,
        "user_message": (question or "").strip(),
        "status": "running",
        "missing_input": None,
        "error_message": "",
        "error_messages": [],
        "attachments_present": bool(attachment_paths),
        "attachment_paths": list(attachment_paths or []),
        "parsed_transactions": [],
        "tool_plan": [],
        "next_step": 0,
        "tool_calls": [],
        "tool_outputs": {},
        "warnings": [],
        "answer": "",
        "has_transaction_data": False,
    }
    state = GRAPH.invoke(initial_state)
    return {
        "answer": state["answer"],
        "tool_calls": state["tool_calls"],
        "supporting_data": state["tool_outputs"],
        "warnings": state["warnings"],
        "status": state["status"],
        "error_message": state["error_message"],
        "missing_input": state["missing_input"],
    }
