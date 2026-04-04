from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    compose_answer_node,
    finalize_node,
    ingestion_guard_node,
    planner_node,
    safety_filter_node,
    tool_executor_node,
    validate_session_node,
)
from app.agent.state import AgentState


def _route_after_validate(state: AgentState) -> str:
    if state["status"] == "error":
        return "finalize"
    return "ingestion_guard"


def _route_after_planner(state: AgentState) -> str:
    if state["status"] in {"error", "needs_ingestion"}:
        return "finalize"
    if not state["plan"]:
        return "compose_answer"
    return "tool_executor"


def _route_after_executor(state: AgentState) -> str:
    if state["next_step"] < len(state["plan"]):
        return "tool_executor"
    return "compose_answer"


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("validate_session", validate_session_node)
    graph.add_node("ingestion_guard", ingestion_guard_node)
    graph.add_node("planner", planner_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("compose_answer", compose_answer_node)
    graph.add_node("safety_filter", safety_filter_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "validate_session")
    graph.add_conditional_edges(
        "validate_session",
        _route_after_validate,
        {"ingestion_guard": "ingestion_guard", "finalize": "finalize"},
    )
    graph.add_edge("ingestion_guard", "planner")
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "tool_executor": "tool_executor",
            "compose_answer": "compose_answer",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "tool_executor",
        _route_after_executor,
        {"tool_executor": "tool_executor", "compose_answer": "compose_answer"},
    )
    graph.add_edge("compose_answer", "safety_filter")
    graph.add_edge("safety_filter", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
