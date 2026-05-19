from __future__ import annotations

from typing import Any

from mini_rag.capabilities.attendance.formatter import format_attendance_result
from mini_rag.capabilities.calendar.formatter import format_calendar_result
from mini_rag.capabilities.datetime.formatter import format_datetime_result


def format_tool_result(tool_name: str, result: dict[str, Any], context: str = "") -> str:
    if tool_name == "get_current_datetime":
        return format_datetime_result(result, context=context)
    if tool_name == "query_attendance_summary":
        return format_attendance_result(result)
    if tool_name == "manage_company_calendar":
        return format_calendar_result(result)
    if result.get("error"):
        return f"工具调用失败：{result.get('error')}"
    return str(result)
