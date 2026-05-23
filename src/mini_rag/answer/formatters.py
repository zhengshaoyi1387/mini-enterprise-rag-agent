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
    if tool_name == "skill":
        if result.get("error"):
            return f"Skill 调用失败：{result.get('error')}"
        skill_name = str(result.get("skill_name") or "skill")
        payload = result.get("result") if isinstance(result.get("result"), dict) else {}
        if skill_name == "attendance_insight" and payload:
            period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
            overview = payload.get("overview") if isinstance(payload.get("overview"), dict) else {}
            patterns = payload.get("patterns") if isinstance(payload.get("patterns"), list) else []
            return (
                f"attendance_insight 已完成 {period.get('start_date', '')} 至 {period.get('end_date', '')} 的考勤洞察分析："
                f"异常记录 {payload.get('total_abnormal_records', overview.get('total_abnormal_records', 0))} 条，"
                f"识别模式 {len(patterns)} 个。"
            )
        if skill_name == "policy_gap_checker" and payload:
            return f"policy_gap_checker 已完成证据缺口分析：overall={payload.get('overall', '')}。"
        return f"{skill_name} 已执行完成。"
    if result.get("error"):
        return f"工具调用失败：{result.get('error')}"
    return str(result)
