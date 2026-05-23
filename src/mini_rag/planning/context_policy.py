from __future__ import annotations

import re
from typing import Any

from mini_rag.capabilities.calendar.resolver import compact_calendar_events
from mini_rag.graph.utils import strip_citations_and_metadata, truncate

SENSITIVE_TOOL_INPUT_KEYS = {"file_path", "db_path", "query", "user_id", "role"}
CONTEXT_REFERENCE_RE = re.compile(
    r"(第[一二三四五六七八九十0-9]+个|这个|那个|刚才|上面|上述|前面|它|该会议|该日程|这些|它们|全部|所有)"
)


def clean_tool_input_for_context(tool_input: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in tool_input.items()
        if str(key) not in SENSITIVE_TOOL_INPUT_KEYS and not str(key).startswith("_")
    }


def turn_to_history_item(turn: Any) -> dict[str, Any]:
    answer = getattr(turn, "memory_answer", "") or strip_citations_and_metadata(getattr(turn, "answer", ""))
    return {
        "question": getattr(turn, "question", ""),
        "standalone_query": getattr(turn, "standalone_query", ""),
        "answer": getattr(turn, "answer", ""),
        "memory_answer": answer,
        "intent": getattr(turn, "intent", ""),
        "topic": getattr(turn, "topic", ""),
        "entities": getattr(turn, "entities", []),
        "created_at": getattr(turn, "created_at", 0.0),
    }


def extract_previous_tool_context(turns: list[Any]) -> dict[str, Any]:
    """Return the latest compact, planner-safe tool context."""

    for turn in reversed(turns or []):
        trace = getattr(turn, "trace", {}) or {}
        if not isinstance(trace, dict):
            continue
        context = trace.get("current_tool_context") or trace.get("tool_context")
        if not isinstance(context, dict) or not context:
            continue
        tool_input = context.get("tool_input") if isinstance(context.get("tool_input"), dict) else {}
        previous = {
            "domain": context.get("domain"),
            "tool_name": context.get("tool_name"),
            "tool_input": clean_tool_input_for_context(tool_input),
            "result_summary": str(context.get("result_summary") or "")[:700],
        }
        events = compact_calendar_events(context.get("events"), limit=20)
        if events:
            previous["events"] = events
        trace_id = context.get("trace_id") or trace.get("trace_id")
        if trace_id:
            previous["trace_id"] = trace_id
        return {key: value for key, value in previous.items() if value not in (None, "", {})}
    return {}


def build_context_packet(
    *,
    history: list[dict[str, Any]],
    previous_tool_context: dict[str, Any],
    question: str | None = None,
) -> dict[str, Any]:
    """Build the compact context packet passed to the planning LLM."""

    last_turn = history[-1] if history else {}
    planning_context: dict[str, Any] = {}
    if last_turn:
        planning_context["last_turn"] = {
            "user": str(last_turn.get("question") or "")[:160],
            "standalone_query": str(last_turn.get("standalone_query") or "")[:160],
            "assistant_brief": truncate(
                strip_citations_and_metadata(str(last_turn.get("memory_answer") or last_turn.get("answer") or "")),
                220,
            ),
            "intent": last_turn.get("intent") or "",
            "topic": last_turn.get("topic") or "",
        }

    previous_tool_context = previous_tool_context if isinstance(previous_tool_context, dict) else {}
    if previous_tool_context and should_include_previous_tool_context(question):
        tool_input = previous_tool_context.get("tool_input") if isinstance(previous_tool_context.get("tool_input"), dict) else {}
        planning_context["previous_tool_context"] = {
            "domain": previous_tool_context.get("domain"),
            "tool_name": previous_tool_context.get("tool_name"),
            "tool_input": clean_tool_input_for_context(tool_input),
            "result_summary": truncate(str(previous_tool_context.get("result_summary") or ""), 220),
        }
        events = compact_calendar_events(previous_tool_context.get("events"), limit=20)
        if events:
            planning_context["previous_tool_context"]["events"] = events

    return {key: value for key, value in planning_context.items() if value}


def should_include_previous_tool_context(question: str | None) -> bool:
    text = str(question or "").strip()
    if not text:
        return True
    return bool(CONTEXT_REFERENCE_RE.search(text))
