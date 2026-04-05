from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    compose_answer_node,
    finalize_node,
    ingest_attachments_node,
    planner_node,
    read_input_node,
    safety_filter_node,
    tool_executor_node,
    transaction_guard_node,
)
from app.agent.state import AgentState


def _route_after_guard(state: AgentState) -> str:
    if state["status"] in {"error", "needs_input"}:
        return "finalize"
    return "planner"


def _route_after_planner(state: AgentState) -> str:
    if state["status"] in {"error", "needs_input"}:
        return "finalize"
    if not state["tool_plan"]:
        return "compose_answer"
    return "tool_executor"


def _route_after_executor(state: AgentState) -> str:
    if state["next_step"] < len(state["tool_plan"]):
        return "tool_executor"
    return "compose_answer"


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("read_input", read_input_node)
    graph.add_node("ingest_attachments", ingest_attachments_node)
    graph.add_node("transaction_guard", transaction_guard_node)
    graph.add_node("planner", planner_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("compose_answer", compose_answer_node)
    graph.add_node("safety_filter", safety_filter_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "read_input")
    graph.add_edge("read_input", "ingest_attachments")
    graph.add_edge("ingest_attachments", "transaction_guard")
    graph.add_conditional_edges(
        "transaction_guard",
        _route_after_guard,
        {
            "planner": "planner",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"tool_executor": "tool_executor", "compose_answer": "compose_answer", "finalize": "finalize"},
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
