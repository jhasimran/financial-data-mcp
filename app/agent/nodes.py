from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import COMPOSER_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT
from app.agent.safety import redact_text, sanitize_data
from app.agent.state import AgentState, PlannedToolCall
from app.agent.tool_registry import TRANSACTION_TOOLS, execute_tool
from app.tools.common import TRANSACTION_STORE, get_logger

logger = get_logger(__name__)
CAPABILITY_TOKENS = (
    "what can you do",
    "what do you do",
    "how can you help",
    "help me",
    "capabilities",
    "features",
)


def _max_steps() -> int:
    try:
        raw = int(os.getenv("LANGGRAPH_MAX_STEPS", "4"))
    except ValueError:
        return 4
    return max(1, raw)


def _get_text_from_response(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return str(content)


def _is_capability_question(question: str) -> bool:
    q = question.lower().strip()
    return any(token in q for token in CAPABILITY_TOKENS)


def _capability_answer() -> str:
    return (
        "I can help you ingest PDF statements, summarize spending by category, flag unusual transactions, "
        "provide financial insights, estimate savings plans, and fetch currency, crypto, and stock data. "
        "Upload statements first for transaction-based analysis."
    )


def _anthropic_chat(system_prompt: str, user_prompt: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.getenv("LANGGRAPH_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    llm = ChatAnthropic(model=model, anthropic_api_key=api_key, temperature=0)
    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    return _get_text_from_response(response)


def _heuristic_plan(question: str) -> list[PlannedToolCall]:
    q = question.lower()
    if _is_capability_question(q):
        return []
    plan: list[PlannedToolCall] = []
    target_match = re.search(r"(?:save|savings|target)\D{0,20}(\d+(?:\.\d+)?)", q)
    strategy = "balanced"
    if "aggressive" in q:
        strategy = "aggressive"
    elif "conservative" in q:
        strategy = "conservative"

    fx_match = re.search(r"(\d+(?:\.\d+)?)\s+([a-zA-Z]{3})\s+to\s+([a-zA-Z]{3})", q)
    if "convert" in q and fx_match:
        plan.append(
            {
                "name": "convert_currency",
                "args": {
                    "amount": float(fx_match.group(1)),
                    "from_currency": fx_match.group(2).upper(),
                    "to_currency": fx_match.group(3).upper(),
                },
            }
        )

    if any(token in q for token in ("btc", "bitcoin", "eth", "ethereum", "crypto")):
        asset = "bitcoin" if "bit" in q or "btc" in q else "ethereum"
        plan.append({"name": "get_crypto_price", "args": {"asset": asset, "vs_currency": "usd"}})

    symbol_match = re.search(r"\b[A-Z]{1,5}\b", question)
    if "stock" in q or "quote" in q:
        plan.append(
            {
                "name": "get_stock_quote",
                "args": {"symbol": symbol_match.group(0) if symbol_match else "AAPL"},
            }
        )

    if any(
        k in q
        for k in (
            "save",
            "savings",
            "budget plan",
            "budget planner",
            "reach savings",
            "max savings",
        )
    ):
        args: dict[str, Any] = {"strategy": strategy}
        if target_match:
            args["target_amount"] = float(target_match.group(1))
        plan.append({"name": "plan_savings", "args": args})
    elif any(k in q for k in ("anomaly", "unusual", "spike", "risk", "insight")):
        plan.append({"name": "financial_insights", "args": {}})
    elif any(k in q for k in ("summary", "spend", "budget", "category")):
        plan.append({"name": "get_spending_summary", "args": {}})
    elif any(k in q for k in ("list", "transaction", "recent")):
        plan.append({"name": "list_transactions", "args": {"limit": 20}})

    if not plan:
        plan = [{"name": "financial_insights", "args": {}}]
    return plan[: _max_steps()]


def _plan_with_llm(question: str) -> list[PlannedToolCall] | None:
    response_text = _anthropic_chat(
        PLANNER_SYSTEM_PROMPT,
        f"User question: {question}\nReturn strict JSON plan.",
    )
    if not response_text:
        return None

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning("Planner returned non-JSON response; using heuristic plan.")
        return None

    raw_plan = payload.get("plan")
    if not isinstance(raw_plan, list):
        return None

    plan: list[PlannedToolCall] = []
    for item in raw_plan[: _max_steps()]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        args = item.get("args", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            continue
        plan.append({"name": name, "args": args})

    return plan or None


def validate_session_node(state: AgentState) -> AgentState:
    if not TRANSACTION_STORE.has_session(state["session_id"]):
        state["status"] = "error"
        state["error_message"] = "Unknown session_id. Create a session first."
    return state


def ingestion_guard_node(state: AgentState) -> AgentState:
    state["has_transaction_data"] = TRANSACTION_STORE.has_data(state["session_id"])
    return state


def planner_node(state: AgentState) -> AgentState:
    planned = _plan_with_llm(state["user_question"]) or _heuristic_plan(state["user_question"])
    state["plan"] = planned

    needs_transactions = any(step["name"] in TRANSACTION_TOOLS for step in planned)
    if needs_transactions and not state["has_transaction_data"]:
        state["status"] = "needs_ingestion"
        state["answer"] = "No ingested transactions available. Upload PDFs first."
        state["warnings"].append("Transaction tools require ingestion before chat analysis.")
    return state


def tool_executor_node(state: AgentState) -> AgentState:
    if state["status"] != "running":
        return state

    if state["next_step"] >= len(state["plan"]):
        return state

    step = state["plan"][state["next_step"]]
    name = step["name"]
    args = step.get("args", {})

    state["tool_calls"].append(name)
    try:
        result = execute_tool(name=name, args=args, session_id=state["session_id"])
        state["supporting_data"][name] = sanitize_data(result)
    except Exception:
        logger.exception("Tool execution failed tool=%s", name)
        state["warnings"].append(f"Tool '{name}' failed and was skipped.")

    state["next_step"] += 1
    return state


def compose_answer_node(state: AgentState) -> AgentState:
    if state["status"] == "error":
        state["answer"] = state["error_message"] or "Unable to process the request."
        return state
    if state["status"] == "needs_ingestion":
        return state

    if not state["tool_calls"]:
        if _is_capability_question(state["user_question"]):
            state["answer"] = _capability_answer()
            return state
        state["answer"] = "I could not identify a suitable tool call for your question."
        return state

    llm_prompt = (
        f"Question: {state['user_question']}\n"
        f"Tool calls: {state['tool_calls']}\n"
        f"Supporting data JSON: {json.dumps(state['supporting_data'])}\n"
        "Write a concise answer in plain English."
    )
    composed = _anthropic_chat(COMPOSER_SYSTEM_PROMPT, llm_prompt)
    if composed:
        state["answer"] = composed.strip()
        return state

    # Deterministic fallback for local/testing without API key.
    if "financial_insights" in state["supporting_data"]:
        payload = state["supporting_data"]["financial_insights"]
        insights = payload.get("insights", [])
        anomaly_count = (payload.get("anomalies") or {}).get("count", 0)
        if insights:
            details = " ".join(insights[:2])
            state["answer"] = (
                f"{details} "
                f"Detected anomalies: {anomaly_count}. Next step: review the largest unusual transactions first."
            )
        else:
            state["answer"] = "No major spending risk signals detected."
    elif "get_spending_summary" in state["supporting_data"]:
        summary = state["supporting_data"]["get_spending_summary"]
        total = summary.get("total_spend")
        categories = summary.get("totals_by_category", {})
        top_categories = sorted(
            categories.items(),
            key=lambda item: float(item[1]),
            reverse=True,
        )[:3]
        if top_categories:
            top_text = ", ".join(f"{name}: {amount} USD" for name, amount in top_categories)
            state["answer"] = f"Total spending is {total} USD. Top categories are {top_text}."
        else:
            state["answer"] = f"Total spending in your ingested data is {total} USD."
    elif "list_transactions" in state["supporting_data"]:
        count = state["supporting_data"]["list_transactions"].get("count", 0)
        state["answer"] = f"I found {count} transactions in your ingested documents."
    elif "convert_currency" in state["supporting_data"]:
        converted = state["supporting_data"]["convert_currency"].get("converted")
        to_cur = state["supporting_data"]["convert_currency"].get("to_currency", "")
        state["answer"] = f"Converted amount is {converted} {to_cur}."
    elif "get_crypto_price" in state["supporting_data"]:
        px = state["supporting_data"]["get_crypto_price"].get("price")
        asset = state["supporting_data"]["get_crypto_price"].get("asset", "asset")
        cur = state["supporting_data"]["get_crypto_price"].get("vs_currency", "usd")
        state["answer"] = f"{asset} is currently priced at {px} {cur}."
    elif "get_stock_quote" in state["supporting_data"]:
        px = state["supporting_data"]["get_stock_quote"].get("price")
        symbol = state["supporting_data"]["get_stock_quote"].get("symbol", "stock")
        state["answer"] = f"{symbol} is currently trading around {px} USD."
    elif "plan_savings" in state["supporting_data"]:
        planner = state["supporting_data"]["plan_savings"]
        max_savings = planner.get("max_savings_estimate")
        target_amount = planner.get("target_amount")
        target_met = planner.get("target_met")
        recommendations = planner.get("recommendations", [])
        top_recos = recommendations[:3] if isinstance(recommendations, list) else []
        reco_text = ", ".join(
            f"{item.get('category')}: cut {item.get('suggested_cut')} USD"
            for item in top_recos
            if isinstance(item, dict)
        )
        if target_amount is not None:
            if target_met:
                state["answer"] = (
                    f"You can likely reach your {target_amount} USD savings target. "
                    f"Estimated max monthly savings is {max_savings} USD."
                )
            else:
                gap = round(float(target_amount) - float(max_savings), 2)
                state["answer"] = (
                    f"Based on historical spending, the estimated max monthly savings is {max_savings} USD, "
                    f"which is below your {target_amount} USD target by {gap} USD."
                )
        else:
            state["answer"] = (
                f"Based on historical patterns, your estimated max monthly savings is {max_savings} USD."
            )
        if reco_text:
            state["answer"] = f"{state['answer']} Suggested cuts: {reco_text}."
    else:
        state["answer"] = "I completed the request using available tools."

    return state


def safety_filter_node(state: AgentState) -> AgentState:
    state["answer"] = redact_text(state["answer"])
    state["warnings"] = [redact_text(warning) for warning in state["warnings"]]
    state["supporting_data"] = sanitize_data(state["supporting_data"])
    return state


def finalize_node(state: AgentState) -> AgentState:
    if state["status"] == "running":
        state["status"] = "done"
    return state
