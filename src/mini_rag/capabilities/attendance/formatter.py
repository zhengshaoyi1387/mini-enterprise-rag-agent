from __future__ import annotations

from typing import Any

STATUS_LABELS = {
    "present": "正常出勤",
    "late": "迟到",
    "leave": "请假",
    "absent": "缺勤",
}


def _status_label(result: dict[str, Any]) -> str:
    status_filter = result.get("status_filter") or (result.get("filters") or {}).get("status_filter")
    status_filters = result.get("status_filters") or (result.get("filters") or {}).get("status_filters") or []
    if status_filter:
        return STATUS_LABELS.get(str(status_filter), str(status_filter))
    if status_filters:
        return "、".join(STATUS_LABELS.get(str(status), str(status)) for status in status_filters)
    return ""


def format_attendance_result(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"工具调用失败：{result.get('error')}"

    status_label = _status_label(result)
    filtered_count = result.get("filtered_count")
    records = result.get("records") or []
    start_date = result.get("start_date")
    end_date = result.get("end_date")

    if status_label:
        if records:
            people: list[str] = []
            limit = 12
            for record in records[:limit]:
                detail = str(record.get("name") or "").strip()
                department = str(record.get("department") or "").strip()
                check_in = str(record.get("check_in") or "").strip()
                status = str(record.get("status") or "").strip()
                if department:
                    detail += f"（{department}"
                    if status and len(result.get("status_filters") or []) > 1:
                        detail += f"，{STATUS_LABELS.get(status, status)}"
                    if check_in:
                        detail += f"，打卡 {check_in}"
                    detail += "）"
                elif check_in:
                    detail += f"（打卡 {check_in}）"
                if detail:
                    people.append(detail)
            suffix = "；".join(people)
            if len(records) > limit:
                suffix += f"；仅展示前 {limit} 条，共 {len(records)} 条记录"
            return f"{start_date} 至 {end_date} 共有 {filtered_count} 条{status_label}记录：{suffix}。"
        return f"{start_date} 至 {end_date} 共有 {filtered_count or 0} 条{status_label}记录。"

    summary = result.get("summary") or {}
    return (
        f"{start_date} 至 {end_date} 的考勤汇总："
        f"记录 {summary.get('total_records', 0)} 条，出勤 {summary.get('present', 0)}，"
        f"迟到 {summary.get('late', 0)}，请假 {summary.get('leave', 0)}，缺勤 {summary.get('absent', 0)}，"
        f"出勤率 {summary.get('attendance_rate', '0.00%')}，迟到率 {summary.get('late_rate', '0.00%')}。"
    )
