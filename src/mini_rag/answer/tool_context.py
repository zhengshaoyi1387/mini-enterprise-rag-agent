from __future__ import annotations

from typing import Any

from mini_rag.answer.formatters import format_tool_result
from mini_rag.capabilities.attendance.service import build_attendance_tool_context
from mini_rag.capabilities.calendar.service import build_calendar_tool_context
from mini_rag.capabilities.datetime.service import build_datetime_tool_context


def _clean_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"file_path", "query", "user_id", "role"} and not str(key).startswith("_")
    }


def build_current_tool_context(tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    clean_payload = _clean_input(payload)
    if tool_name == "manage_company_calendar":
        return build_calendar_tool_context(clean_payload, result)
    if tool_name == "query_attendance_summary":
        return build_attendance_tool_context(clean_payload, result)
    if tool_name == "get_current_datetime":
        return build_datetime_tool_context(clean_payload, result)
    return {
        "domain": "tool",
        "tool_name": tool_name,
        "tool_input": clean_payload,
        "result_summary": format_tool_result(tool_name, result),
        "trace_id": None,
    }
