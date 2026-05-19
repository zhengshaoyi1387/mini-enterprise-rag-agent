from __future__ import annotations

from typing import Any

from mini_rag.capabilities.attendance.formatter import format_attendance_result


def build_attendance_tool_context(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": "attendance",
        "tool_name": "query_attendance_summary",
        "tool_input": dict(payload),
        "result_summary": format_attendance_result(result),
        "trace_id": None,
    }
