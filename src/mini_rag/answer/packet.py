from __future__ import annotations

import json
from typing import Any

from mini_rag.core.contracts import AnswerPacket


def _truncate(value: str, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def compact_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        title_path = str(item.get("title_path") or "")
        chunk_id = str(item.get("chunk_id") or "")
        key = (source, title_path, chunk_id)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "source": source,
                "title_path": title_path,
                "chunk_id": chunk_id,
                "text": _truncate(str(item.get("preview") or ""), 320),
            }
        )
    return [item for item in sources if item.get("source") or item.get("text")]


def _compact_calendar_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: event.get(key)
        for key in ("date", "weekday_zh", "time", "title", "location", "type", "department")
        if event.get(key) not in (None, "", [], {})
    }


def _compact_calendar_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    events = tool_result.get("events") if isinstance(tool_result.get("events"), list) else []
    compact_events: list[dict[str, Any]] = []
    for event in events[:20]:
        if not isinstance(event, dict):
            continue
        compact_event = _compact_calendar_event(event)
        if compact_event:
            compact_events.append(compact_event)
    return compact_events


def _compact_attendance_result(result: dict[str, Any]) -> dict[str, Any]:
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    output: dict[str, Any] = {}
    for key in ("start_date", "end_date", "status_filter", "status_filters", "filtered_count", "filtered_count_by_status"):
        if tool_result.get(key) not in (None, "", [], {}):
            output[key] = tool_result.get(key)
    if isinstance(tool_result.get("summary"), dict):
        output["attendance_summary"] = tool_result.get("summary")
    for source_key, target_key in (
        ("by_department", "attendance_by_department"),
        ("by_employee", "attendance_by_employee"),
        ("records", "attendance_records"),
    ):
        values = tool_result.get(source_key)
        if isinstance(values, list) and values:
            output[target_key] = values[:20]
    return output


def _wanted_datetime_range_keys(context: str) -> set[str]:
    keys: set[str] = set()
    checks = (
        ("后天", "day_after_tomorrow"),
        ("明天", "tomorrow"),
        ("昨天", "yesterday"),
        ("今天", "today"),
        ("当前", "today"),
        ("现在", "today"),
        ("上周", "last_week"),
        ("下周", "next_week"),
        ("本周", "this_week"),
        ("这周", "this_week"),
        ("上个月", "last_month"),
        ("上月", "last_month"),
        ("下个月", "next_month"),
        ("下月", "next_month"),
        ("本月", "this_month"),
        ("这个月", "this_month"),
    )
    for token, key in checks:
        if token in context:
            keys.add(key)
    return keys or {"today"}


def _compact_datetime_result(result: dict[str, Any], datetime_context: str = "") -> dict[str, Any]:
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    output: dict[str, Any] = {}
    for key in ("current_date", "current_time", "weekday_zh", "timezone", "warning"):
        if tool_result.get(key) not in (None, "", [], {}):
            output[key] = tool_result.get(key)
    ranges = tool_result.get("ranges")
    if isinstance(ranges, dict):
        compact_ranges: dict[str, Any] = {}
        result_context = f"{datetime_context}\n{result.get('objective') or ''}\n{result.get('result_summary') or ''}".lower()
        wanted_keys = _wanted_datetime_range_keys(result_context)
        for key in wanted_keys:
            value = ranges.get(key)
            if not isinstance(value, dict):
                continue
            compact_range = {
                range_key: value.get(range_key)
                for range_key in ("start_date", "end_date")
                if value.get(range_key) not in (None, "", [], {})
            }
            if compact_range:
                compact_ranges[str(key)] = compact_range
        if compact_ranges:
            output["ranges"] = compact_ranges
    return output


def compact_task_results(results: list[dict[str, Any]] | None, *, datetime_context: str = "") -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for idx, result in enumerate(results or [], start=1):
        if not isinstance(result, dict):
            continue
        item: dict[str, Any] = {
            "序号": idx,
            "类型": result.get("kind"),
            "目标": result.get("objective") or result.get("query"),
        }
        if result.get("kind") == "tool":
            if result.get("tool_name"):
                item["工具"] = result.get("tool_name")
            if result.get("action"):
                item["动作"] = result.get("action")
            if result.get("status"):
                item["任务状态"] = result.get("status")
            tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
            if tool_result.get("status"):
                item["工具状态"] = tool_result.get("status")
            if tool_result.get("message"):
                item["工具消息"] = _truncate(str(tool_result.get("message") or ""), 240)
            if result.get("tool_name") == "manage_company_calendar" and result.get("action") == "query":
                events = _compact_calendar_events(result)
                if events:
                    item["calendar_events"] = events
            if result.get("tool_name") == "manage_company_calendar" and result.get("action") in {"create", "update"}:
                event = tool_result.get("event")
                if isinstance(event, dict):
                    compact_event = _compact_calendar_event(event)
                    if compact_event:
                        item["calendar_event"] = compact_event
            if result.get("tool_name") == "query_attendance_summary":
                attendance = _compact_attendance_result(result)
                if attendance:
                    item.update(attendance)
            if result.get("tool_name") == "get_current_datetime":
                datetime_facts = _compact_datetime_result(result, datetime_context=datetime_context)
                if datetime_facts:
                    item["datetime_facts"] = datetime_facts
            has_structured_payload = any(
                key in item
                for key in (
                    "calendar_events",
                    "calendar_event",
                    "attendance_summary",
                    "attendance_by_department",
                    "attendance_by_employee",
                    "attendance_records",
                    "datetime_facts",
                )
            )
            if result.get("result_summary"):
                item["结果"] = _truncate(str(result.get("result_summary") or ""), 900)
            elif isinstance(result.get("tool_result"), dict) and not has_structured_payload:
                item["结果"] = _truncate(json.dumps(result.get("tool_result"), ensure_ascii=False, default=str), 900)
        else:
            sources = compact_sources([s for s in (result.get("sources") or []) if isinstance(s, dict)])
            related_sources = compact_sources([s for s in (result.get("related_sources") or []) if isinstance(s, dict)])
            if sources:
                item["证据"] = sources
            elif str(result.get("status") or "").lower() in {"empty", "no_evidence", "insufficient_evidence"}:
                if related_sources:
                    item["证据情况"] = "当前可访问知识库未找到完整明确依据，但检索到以下相关内容；只能作为相关参考，不能直接当作完整结论。"
                    item["相关内容"] = related_sources
                else:
                    item["证据情况"] = "当前可访问知识库未找到明确支持证据。"
        compact.append({k: v for k, v in item.items() if v not in (None, "", [], {})})
    return compact


def build_answer_packet(state: dict[str, Any]) -> AnswerPacket:
    route = str(state.get("route") or "direct")
    datetime_context = f"{state.get('question') or ''}\n{state.get('standalone_query') or ''}".lower()
    compact_results = compact_task_results(
        [item for item in (state.get("task_results") or []) if isinstance(item, dict)],
        datetime_context=datetime_context,
    )
    sources = compact_sources([item for item in (state.get("sources") or state.get("supporting_sources") or []) if isinstance(item, dict)])
    messages: list[str] = []
    final_answer = str(state.get("final_answer") or "").strip()
    if final_answer:
        messages.append(final_answer)
    resolved_time_facts = state.get("resolved_time_facts") if isinstance(state.get("resolved_time_facts"), list) else []
    safety_events = [
        item
        for item in (state.get("audit_events") or []) + (state.get("observations") or [])
        if isinstance(item, dict)
        and (
            str(item.get("decision") or "") == "blocked"
            or str(item.get("status") or "") in {"blocked", "need_clarification", "refused"}
            or "safety" in str(item.get("type") or "").lower()
        )
    ]
    permission_events = [
        item
        for item in (state.get("audit_events") or [])
        if isinstance(item, dict) and ("permission" in str(item.get("event") or "") or item.get("decision") == "blocked")
    ]
    task_results = [item for item in (state.get("task_results") or []) if isinstance(item, dict)]
    rag_results = [item for item in task_results if str(item.get("kind") or "").lower() == "rag"]
    rag_empty = [
        item for item in rag_results if str(item.get("status") or "").lower() in {"empty", "no_evidence", "insufficient_evidence"}
    ]
    non_rag_results = [item for item in task_results if str(item.get("kind") or "").lower() != "rag"]
    execution_status = "success"
    if state.get("error") or route == "reject":
        execution_status = "blocked"
    elif state.get("intent") in {"need_clarification", "clarification_required"}:
        execution_status = "need_clarification"
    elif any(str(item.get("status") or "") in {"error", "failed", "blocked"} for item in task_results):
        execution_status = "partial"
    elif rag_empty and rag_results and len(rag_empty) == len(rag_results) and not non_rag_results:
        execution_status = "insufficient_evidence"
    elif rag_empty and rag_results:
        execution_status = "partial"
    packet_results = list(compact_results)
    if resolved_time_facts:
        packet_results.insert(0, {"类型": "resolved_time_facts", "时间事实": resolved_time_facts})
    if safety_events:
        packet_results.append({"类型": "safety_events", "安全事件": safety_events[:8]})
    if permission_events:
        packet_results.append({"类型": "permission_events", "权限事件": permission_events[:8]})
    packet_results.append({"类型": "execution_status", "状态": execution_status})
    return AnswerPacket(
        route=route if route in {"direct", "rag", "tool", "reject"} else "direct",
        status=execution_status if execution_status in {"success", "partial", "blocked", "need_clarification", "failed", "insufficient_evidence"} else "ready",  # type: ignore[arg-type]
        messages=tuple(messages),
        task_results=tuple(packet_results),  # type: ignore[arg-type]
        sources=tuple(sources),
        should_call_llm=True,
    )


__all__ = ["AnswerPacket", "build_answer_packet", "compact_sources", "compact_task_results"]
