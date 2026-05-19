from __future__ import annotations

from typing import Any

from mini_rag.capabilities.calendar.formatter import format_calendar_result
from mini_rag.capabilities.calendar.resolver import compact_calendar_events


def build_calendar_tool_context(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    context = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": dict(payload),
        "result_summary": format_calendar_result(result),
        "trace_id": None,
    }
    if result.get("action") == "query":
        events = compact_calendar_events(result.get("events"), limit=20)
        if events:
            context["events"] = events
    return context
