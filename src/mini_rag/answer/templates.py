from __future__ import annotations

import re
from typing import Any


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def friendly_tool_error(tool_name: str, result: dict[str, Any], role: str | None = None, action: str | None = None) -> str:
    error = str(result.get("error") or "")
    action = str(action or result.get("action") or "")
    if tool_name == "manage_company_calendar" and error == "permission denied" and action in {"create", "update", "delete"}:
        return "你没有权限修改公司日程。只有 admin 可以新增、更新或删除日程。"
    if tool_name == "manage_company_calendar" and error == "event not found" and action in {"update", "delete"}:
        return "没有找到指定 event_id 的公司日程，本次没有更新或删除。"
    if tool_name == "manage_company_calendar" and error == "update verification failed":
        return "日程更新结果与请求不一致，本次修改未被确认为成功。请指定 event_id 后重试。"
    if error == "invalid date format":
        if tool_name == "query_attendance_summary":
            return "我需要一个明确的日期范围才能查询考勤。你可以说“昨天”、“上周”或“2026-05-01 到 2026-05-07”。"
        if tool_name == "manage_company_calendar":
            return "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"
    return "工具执行失败，请检查请求参数后再试。"


def friendly_tool_validation_error(tool_name: str, exc: Exception) -> str:
    detail = str(exc)
    if tool_name == "query_attendance_summary" and any(field in detail for field in ("start_date", "end_date")):
        return "我需要一个明确的日期范围才能查询考勤。你可以说“昨天”、“上周”或“2026-05-01 到 2026-05-07”。"
    if tool_name == "manage_company_calendar" and any(field in detail for field in ("start_date", "end_date")):
        return "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"
    if tool_name == "manage_company_calendar" and "title" in detail:
        return "我还缺少日程标题，请补充要新增或更新的日程名称。"
    if tool_name == "manage_company_calendar" and "event_id" in detail:
        return "我还缺少要修改或删除的日程 ID。"
    return "我还缺少执行该能力所需的必要信息，请补充具体日期、时间或事件信息。"


def friendly_permission_answer(role: str, tool_name: str, action: str | None = None) -> str:
    action = str(action or "*").lower()
    if tool_name == "manage_company_calendar" and action == "query":
        return "你当前角色无法查看公司内部日程，请使用员工或管理员账号登录后再查询。"
    if tool_name == "manage_company_calendar" and action in {"create", "update", "delete"}:
        return "你没有权限修改公司日程，也无权执行该操作；当前角色权限不足。只有 admin 可以新增、更新或删除日程。"
    if tool_name == "query_attendance_summary":
        return "你当前角色无权查看该范围的公司内部考勤数据；部门、全员或明细查询需要 HR 或 admin 权限。"
    return "你当前角色没有权限使用该企业能力。"


def permission_required_direct_answer(state: dict[str, Any]) -> str:
    topic = str(state.get("topic") or "").lower()
    standalone = str(state.get("standalone_query") or state.get("question") or "")
    text = f"{topic} {standalone}"
    if "calendar_write" in topic or any(token in topic for token in ("manage_company_calendar.create", "manage_company_calendar.update", "manage_company_calendar.delete")):
        return "你没有权限修改公司日程，也无权执行该操作；当前角色权限不足。只有 admin 可以新增、更新或删除日程。"
    if "calendar" in topic or "日程" in text:
        return "你当前角色无法查看公司内部日程，请使用员工或管理员账号登录后再查询。"
    if "attendance" in topic or "考勤" in text:
        return "你当前角色无权查看该范围的公司内部考勤数据；部门、全员或明细查询需要 HR 或 admin 权限。"
    return "你当前角色无权使用该企业能力，请切换到有权限的账号后再试。"


def clarification_required_direct_answer(state: dict[str, Any]) -> str:
    topic = str(state.get("topic") or "").lower()

    def label_fields(values: list[Any]) -> str:
        labels = {
            "date": "日期",
            "time": "时间",
            "title": "标题",
            "event_id": "event_id",
            "start_date/end_date": "日期范围",
        }
        output: list[str] = []
        for raw in values:
            for part in re.split(r"[,，、/]+", str(raw or "")):
                part = part.strip()
                if not part:
                    continue
                label = labels.get(part, part)
                if label not in output:
                    output.append(label)
        return "、".join(output)

    question = str(state.get("standalone_query") or state.get("question") or "")
    missing = label_fields(_coerce_list(state.get("missing_required_slots")))
    missing_raw = [str(item) for item in _coerce_list(state.get("missing_required_slots"))]
    if any("event_id" in item for item in missing_raw) and ("calendar" in topic or "日程" in question):
        return "请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。"
    if missing:
        return f"我还缺少必要信息：{missing}。请补充后我再继续处理。"
    issues = state.get("plan_validation", {}).get("validation_issues") if isinstance(state.get("plan_validation"), dict) else []
    issue_fields = label_fields([item.get("field") for item in _coerce_list(issues) if isinstance(item, dict) and item.get("field")])
    issue_raw = [str(item.get("field") or "") for item in _coerce_list(issues) if isinstance(item, dict)]
    if any("event_id" in item for item in issue_raw) and ("calendar" in topic or "日程" in question):
        return "请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。"
    if issue_fields:
        return f"我还缺少必要信息：{issue_fields}。请补充具体日期、时间或事件信息后我再继续处理。"
    if "calendar" in topic:
        return "请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。"
    return "我还需要更具体的信息才能继续处理，请补充目标、日期或标识。"
