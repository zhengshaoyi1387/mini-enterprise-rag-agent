from __future__ import annotations

from typing import Any

from mini_rag.capabilities.calendar.resolver import compact_calendar_events


def _event_text(event: dict[str, Any]) -> str:
    date_text = str(event.get("date") or "").strip()
    weekday = str(event.get("weekday_zh") or "").strip()
    if weekday:
        date_text = f"{date_text} {weekday}".strip()
    time_text = str(event.get("time") or "").strip()
    title = str(event.get("title") or "").strip()
    location = str(event.get("location") or "").strip()
    main = " ".join(part for part in (date_text, time_text, title) if part)
    if location:
        return f"{main}（{location}）"
    return main


def _query_label(events: list[dict[str, Any]]) -> str:
    event_types = {str(event.get("type") or "").strip().lower() for event in events if isinstance(event, dict)}
    if event_types == {"meeting"}:
        return "公司会议安排"
    return "公司日程"


def format_calendar_result(result: dict[str, Any]) -> str:
    if result.get("error"):
        error = str(result.get("error") or "")
        action = str(result.get("action") or "")
        if error == "event not found" and action in {"update", "delete"}:
            return "没有找到指定 event_id 的公司日程，本次没有更新或删除。"
        if error == "permission denied" and action in {"create", "update", "delete"}:
            return "你没有权限修改公司日程。只有 admin 可以新增、更新或删除日程。"
        if error == "update verification failed":
            return "日程更新结果与请求不一致，本次修改未被确认为成功。请指定 event_id 后重试。"
        return f"工具调用失败：{error}"

    action = str(result.get("action") or "").strip().lower()
    if action == "query":
        events = [event for event in (result.get("events") or []) if isinstance(event, dict)]
        if not events:
            return f"{result.get('start_date')} 至 {result.get('end_date')} 没有匹配的公司日程。"
        lines = [f"{result.get('start_date')} 至 {result.get('end_date')} 的{_query_label(events)}："]
        for event in compact_calendar_events(events, limit=20):
            text = _event_text(event)
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)

    if action == "delete":
        message = str(result.get("message") or "").strip()
        event_id = str(result.get("event_id") or "").strip()
        if message:
            return message
        return f"公司日程已删除：{event_id}。" if event_id else "公司日程已删除。"

    if action in {"create", "update"} and isinstance(result.get("event"), dict):
        event_text = _event_text(result.get("event") or {})
        message = str(result.get("message") or ("公司日程已新增" if action == "create" else "公司日程已更新")).strip()
        return f"{message}：{event_text}。" if event_text else f"{message}。"

    return str(result.get("message") or f"公司日程已{result.get('status', '处理')}")
