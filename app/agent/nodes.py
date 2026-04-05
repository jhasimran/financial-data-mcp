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
from app.agent.tool_registry import execute_tool
from app.tools.common import TRANSACTION_STORE, get_logger
from app.tools.ingestion import ingest_financial_documents
from app.tools.transactions import set_ingested_transactions

logger = get_logger(__name__)
CAPABILITY_TOKENS = (
    "what can you do",
    "what do you do",
    "how can you help",
    "help me",
    "capabilities",
    "features",
)
USER_FACING_TOOLS = {
    "list_transactions",
    "get_spending_summary",
    "flag_anomalies",
    "financial_insights",
    "plan_savings",
}


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
        "I can analyze uploaded financial statements to summarize spending, flag unusual transactions, "
        "generate financial insights, and estimate savings plans. Upload statement PDFs, then ask what you "
        "want to analyze."
    )


def _anthropic_chat(system_prompt: str, user_prompt: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.getenv("LANGGRAPH_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    llm = ChatAnthropic(model=model, anthropic_api_key=api_key, temperature=0)
    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    return _get_text_from_response(response)


def _dedupe_plan(plan: list[PlannedToolCall]) -> list[PlannedToolCall]:
    deduped: list[PlannedToolCall] = []
    seen: set[str] = set()
    for step in plan:
        name = step["name"]
        if name in seen:
            continue
        seen.add(name)
        deduped.append(step)
    return deduped[: _max_steps()]


def _heuristic_plan(question: str) -> list[PlannedToolCall]:
    q = question.lower().strip()
    if not q:
        return []
    if _is_capability_question(q):
        return []

    plan: list[PlannedToolCall] = []
    target_match = re.search(r"(?:save|savings|target)\D{0,20}(\d+(?:\.\d+)?)", q)
    strategy = "balanced"
    if "aggressive" in q:
        strategy = "aggressive"
    elif "conservative" in q:
        strategy = "conservative"

    if any(
        token in q
        for token in (
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

    if any(token in q for token in ("summary", "spend", "category", "top spending")):
        plan.append({"name": "get_spending_summary", "args": {}})

    if any(token in q for token in ("anomaly", "unusual", "spike", "suspicious")):
        plan.append({"name": "flag_anomalies", "args": {}})

    if any(token in q for token in ("insight", "insights", "risk", "cash flow")) and not plan:
        plan.append({"name": "financial_insights", "args": {}})

    if any(token in q for token in ("list", "transaction", "recent")):
        plan.append({"name": "list_transactions", "args": {"limit": 20}})

    if not plan:
        plan = [{"name": "financial_insights", "args": {}}]
    return _dedupe_plan(plan)


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
        if name not in USER_FACING_TOOLS:
            continue
        plan.append({"name": name, "args": args})

    return _dedupe_plan(plan) or None


def read_input_node(state: AgentState) -> AgentState:
    state["user_message"] = state["user_message"].strip()
    state["attachments_present"] = len(state["attachment_paths"]) > 0
    state["has_transaction_data"] = TRANSACTION_STORE.has_data(state["session_id"])
    return state


def ingest_attachments_node(state: AgentState) -> AgentState:
    if state["status"] != "running" or not state["attachments_present"]:
        return state

    try:
        result = ingest_financial_documents(file_paths=state["attachment_paths"])
        parsed_transactions = result["transactions"]
        state["parsed_transactions"] = parsed_transactions
        state["warnings"].extend(result["warnings"])
        if parsed_transactions:
            set_ingested_transactions(
                transactions=parsed_transactions,
                sources=result["sources"],
                warnings=result["warnings"],
                session_id=state["session_id"],
            )
            state["has_transaction_data"] = True
    except Exception:
        logger.exception("Attachment ingestion failed session=%s", state["session_id"])
        state["status"] = "error"
        state["error_message"] = "Failed to ingest attached financial documents."
        state["error_messages"].append(state["error_message"])
    finally:
        state["attachment_paths"] = []
        state["attachments_present"] = False

    return state


def transaction_guard_node(state: AgentState) -> AgentState:
    if state["status"] != "running":
        return state

    state["has_transaction_data"] = TRANSACTION_STORE.has_data(state["session_id"]) or bool(
        state["parsed_transactions"]
    )
    if not state["has_transaction_data"]:
        state["status"] = "needs_input"
        state["missing_input"] = "transactions"
        state["answer"] = (
            "Please upload a bank or credit card statement PDF so I can analyze your transactions."
        )
        return state

    if not state["user_message"]:
        state["status"] = "needs_input"
        state["missing_input"] = "question"
        if state["parsed_transactions"]:
            state["answer"] = (
                f"I ingested {len(state['parsed_transactions'])} transactions. "
                "What would you like me to analyze next?"
            )
        else:
            state["answer"] = "What would you like me to analyze from your transactions?"
    return state


def planner_node(state: AgentState) -> AgentState:
    if state["status"] != "running":
        return state

    if _is_capability_question(state["user_message"]):
        state["tool_plan"] = []
        return state

    planned = _plan_with_llm(state["user_message"]) or _heuristic_plan(state["user_message"])
    state["tool_plan"] = planned
    return state


def tool_executor_node(state: AgentState) -> AgentState:
    if state["status"] != "running":
        return state

    if state["next_step"] >= len(state["tool_plan"]):
        return state

    step = state["tool_plan"][state["next_step"]]
    name = step["name"]
    args = step.get("args", {})

    state["tool_calls"].append(name)
    try:
        result = execute_tool(name=name, args=args, session_id=state["session_id"])
        state["tool_outputs"][name] = sanitize_data(result)
    except Exception:
        logger.exception("Tool execution failed tool=%s", name)
        state["warnings"].append(f"Tool '{name}' failed and was skipped.")
        state["error_messages"].append(f"Tool execution failed: {name}")

    state["next_step"] += 1
    return state


def _fallback_spending_summary(payload: dict[str, Any]) -> str:
    total = payload.get("total_spend")
    categories = payload.get("totals_by_category", {})
    top_categories = sorted(
        categories.items(),
        key=lambda item: float(item[1]),
        reverse=True,
    )[:3]
    if top_categories:
        top_text = ", ".join(f"{name}: {amount} USD" for name, amount in top_categories)
        return f"Total spending is {total} USD. Top categories are {top_text}."
    return f"Total spending in your ingested data is {total} USD."


def _fallback_anomalies(payload: dict[str, Any]) -> str:
    count = payload.get("count", 0)
    anomalies = payload.get("anomalies", [])
    if not count:
        return "I did not detect any unusual transactions."
    sample = anomalies[0] if anomalies else {}
    merchant = sample.get("merchant")
    amount = sample.get("amount")
    if merchant and amount is not None:
        return f"I found {count} unusual transactions. One example is {merchant} for {amount} USD."
    return f"I found {count} unusual transactions worth reviewing."


def _fallback_insights(payload: dict[str, Any]) -> str:
    insights = payload.get("insights", [])
    if insights:
        return " ".join(insights[:2])
    return "No major spending risk signals detected."


def _fallback_list_transactions(payload: dict[str, Any]) -> str:
    count = payload.get("count", 0)
    return f"I found {count} transactions in your ingested documents."


def _fallback_plan_savings(payload: dict[str, Any]) -> str:
    max_savings = payload.get("max_savings_estimate")
    target_amount = payload.get("target_amount")
    target_met = payload.get("target_met")
    recommendations = payload.get("recommendations", [])
    top_recos = recommendations[:3] if isinstance(recommendations, list) else []
    reco_text = ", ".join(
        f"{item.get('category')}: cut {item.get('suggested_cut')} USD"
        for item in top_recos
        if isinstance(item, dict)
    )

    if target_amount is not None:
        if target_met:
            answer = (
                f"You can likely reach your {target_amount} USD savings target. "
                f"Estimated max monthly savings is {max_savings} USD."
            )
        else:
            gap = round(float(target_amount) - float(max_savings), 2)
            answer = (
                f"Based on historical spending, the estimated max monthly savings is {max_savings} USD, "
                f"which is below your {target_amount} USD target by {gap} USD."
            )
    else:
        answer = f"Based on historical patterns, your estimated max monthly savings is {max_savings} USD."

    if reco_text:
        answer = f"{answer} Suggested cuts: {reco_text}."
    return answer


def compose_answer_node(state: AgentState) -> AgentState:
    if state["status"] == "error":
        state["answer"] = state["error_message"] or "Unable to process the request."
        return state
    if state["status"] == "needs_input":
        return state

    if not state["tool_calls"]:
        if _is_capability_question(state["user_message"]):
            state["answer"] = _capability_answer()
            return state
        state["answer"] = "I could not identify a suitable transaction analysis for your request."
        return state

    llm_prompt = (
        f"Question: {state['user_message']}\n"
        f"Tool calls: {state['tool_calls']}\n"
        f"Supporting data JSON: {json.dumps(state['tool_outputs'])}\n"
        "Write a concise answer in plain English."
    )
    composed = _anthropic_chat(COMPOSER_SYSTEM_PROMPT, llm_prompt)
    if composed:
        state["answer"] = composed.strip()
        return state

    parts: list[str] = []
    outputs = state["tool_outputs"]
    if "get_spending_summary" in outputs:
        parts.append(_fallback_spending_summary(outputs["get_spending_summary"]))
    if "flag_anomalies" in outputs:
        parts.append(_fallback_anomalies(outputs["flag_anomalies"]))
    if "financial_insights" in outputs and "get_spending_summary" not in outputs and "flag_anomalies" not in outputs:
        parts.append(_fallback_insights(outputs["financial_insights"]))
    if "plan_savings" in outputs:
        parts.append(_fallback_plan_savings(outputs["plan_savings"]))
    if "list_transactions" in outputs and not parts:
        parts.append(_fallback_list_transactions(outputs["list_transactions"]))
    if "convert_currency" in outputs:
        converted = outputs["convert_currency"].get("converted")
        to_cur = outputs["convert_currency"].get("to_currency", "")
        parts.append(f"Converted amount is {converted} {to_cur}.")
    if "get_crypto_price" in outputs:
        px = outputs["get_crypto_price"].get("price")
        asset = outputs["get_crypto_price"].get("asset", "asset")
        cur = outputs["get_crypto_price"].get("vs_currency", "usd")
        parts.append(f"{asset} is currently priced at {px} {cur}.")
    if "get_stock_quote" in outputs:
        px = outputs["get_stock_quote"].get("price")
        symbol = outputs["get_stock_quote"].get("symbol", "stock")
        parts.append(f"{symbol} is currently trading around {px} USD.")

    state["answer"] = " ".join(parts) if parts else "I completed the request using available tools."
    return state


def safety_filter_node(state: AgentState) -> AgentState:
    state["answer"] = redact_text(state["answer"])
    state["warnings"] = [redact_text(warning) for warning in state["warnings"]]
    state["tool_outputs"] = sanitize_data(state["tool_outputs"])
    return state


def finalize_node(state: AgentState) -> AgentState:
    if state["status"] == "running":
        state["status"] = "done"
    return state
