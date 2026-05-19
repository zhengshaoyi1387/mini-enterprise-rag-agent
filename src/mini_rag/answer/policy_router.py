from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnswerPolicyDecision:
    strategy: str
    should_call_llm: bool
    reason: str = ""


def _task_kinds(state: dict[str, Any]) -> set[str]:
    return {
        str(item.get("kind") or "").lower()
        for item in (state.get("task_results") or [])
        if isinstance(item, dict) and item.get("kind")
    }


def _asks_event_id_sentinel_safety(state: dict[str, Any]) -> bool:
    text = f"{state.get('question') or ''}\n{state.get('standalone_query') or ''}".lower()
    if "event_id" not in text:
        return False
    return any(token in text for token in ("event_id=all", "event_id = all", "event_id=multiple", "event_id_from", "event_id=*")) and any(
        token in text for token in ("为什么", "不能", "不允许", "why", "cannot")
    )


def route_answer_policy(state: dict[str, Any]) -> AnswerPolicyDecision:
    route = str(state.get("route") or "direct")
    intent = str(state.get("intent") or "")
    if _asks_event_id_sentinel_safety(state):
        return AnswerPolicyDecision("safety_llm", True, "calendar event_id sentinel safety explanation")
    if route == "reject":
        return AnswerPolicyDecision("refusal_llm", True, "reject route")
    if route == "direct" and intent == "smalltalk":
        return AnswerPolicyDecision("direct_llm", True, "smalltalk")
    if intent in {"need_clarification", "clarification_required"}:
        return AnswerPolicyDecision("clarification_llm", True, "clarification intent")
    if intent == "permission_required":
        return AnswerPolicyDecision("refusal_llm", True, "permission intent")

    kinds = _task_kinds(state)
    if "tool" in kinds and "rag" in kinds:
        return AnswerPolicyDecision("synthesis", True, "mixed tool-rag result")
    if kinds == {"rag"} or route == "rag":
        return AnswerPolicyDecision("rag_grounded", True, "pure rag answer")
    if kinds == {"tool"} or route == "tool":
        return AnswerPolicyDecision("tool_llm", True, "pure tool answer")
    if state.get("react_status"):
        return AnswerPolicyDecision("synthesis", True, "react execution result")
    if route == "direct":
        return AnswerPolicyDecision("direct_llm", True, "direct non-template answer")
    return AnswerPolicyDecision("direct_llm", True, "default answer llm")
