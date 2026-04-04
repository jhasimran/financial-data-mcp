from __future__ import annotations

from app.agent.graph import build_agent_graph
from app.agent.state import AgentState

GRAPH = build_agent_graph()


def run_langgraph_chat(session_id: str, question: str) -> dict:
    initial_state: AgentState = {
        "session_id": session_id,
        "user_question": question,
        "status": "running",
        "error_message": "",
        "plan": [],
        "next_step": 0,
        "tool_calls": [],
        "supporting_data": {},
        "warnings": [],
        "answer": "",
        "has_transaction_data": False,
    }
    state = GRAPH.invoke(initial_state)
    return {
        "answer": state["answer"],
        "tool_calls": state["tool_calls"],
        "supporting_data": state["supporting_data"],
        "warnings": state["warnings"],
        "status": state["status"],
        "error_message": state["error_message"],
    }
