from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from mini_rag.capabilities.attendance.resolver import normalize_attendance_status_fields
from mini_rag.capabilities.calendar.resolver import CALENDAR_UPDATE_FIELDS, flatten_calendar_update_fields, is_unresolved_calendar_event_id
from mini_rag.tools.contracts import validate_tool_input

FinalizeToolInput = Callable[[dict[str, Any], str, dict[str, Any], dict[str, Any] | None, str | None], dict[str, Any]]
RunDatetimeTool = Callable[[dict[str, Any], str], dict[str, Any]]


def normalize_tool_payload_for_action_contract(tool_name: str, payload: dict[str, Any], selected_action: str | None = None) -> None:
    if tool_name == "query_attendance_summary":
        normalize_attendance_status_fields(payload)
        return
    if tool_name != "manage_company_calendar":
        return
    action = str(payload.get("action") or selected_action or "query").strip().lower() or "query"
    payload["action"] = action
    flatten_calendar_update_fields(payload)
    if action == "update":
        for field in CALENDAR_UPDATE_FIELDS:
            if field in payload and payload.get(field) in (None, ""):
                payload.pop(field, None)
    if action not in {"create", "update", "delete"}:
        return
    if action in {"update", "delete"} and is_unresolved_calendar_event_id(payload.get("event_id")):
        payload.pop("event_id", None)
    start_date = str(payload.get("start_date") or "").strip()
    end_date = str(payload.get("end_date") or "").strip()
    if not payload.get("date") and start_date and start_date == end_date:
        payload["date"] = start_date
    for query_field in ("start_date", "end_date", "query_scope", "event_type"):
        payload.pop(query_field, None)


def prune_tool_payload_for_action_contract(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name != "manage_company_calendar":
        return payload
    action = str(payload.get("action") or "query").strip().lower() or "query"
    if action == "query":
        allowed = {"action", "start_date", "end_date", "query_scope", "event_type", "department"}
    elif action == "create":
        allowed = {"action", "title", "type", "date", "time", "department", "location", "description"}
    elif action == "update":
        allowed = {"action", "event_id", "title", "type", "date", "time", "department", "location", "description"}
    elif action == "delete":
        allowed = {"action", "event_id"}
    else:
        return payload
    return {key: value for key, value in payload.items() if key in allowed}


def verify_tool_result_consistency(tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
    if tool_name != "manage_company_calendar":
        return
    if result.get("error") or str(payload.get("action") or "").lower() != "update":
        return
    event = result.get("event") if isinstance(result.get("event"), dict) else {}
    mismatches: list[dict[str, str]] = []
    for field in CALENDAR_UPDATE_FIELDS:
        if field not in payload:
            continue
        expected = str(payload.get(field) or "")
        actual = str(event.get(field) or "")
        if actual != expected:
            mismatches.append({"field": field, "expected": expected, "actual": actual})
    if mismatches:
        result["error"] = "update verification failed"
        result["mismatched_fields"] = mismatches
        result["message"] = "日程更新结果与请求不一致"


def build_tool_payload(
    state: dict[str, Any],
    tool_name: str,
    role: str,
    *,
    run_datetime_for_tool: RunDatetimeTool,
    finalize_tool_input: FinalizeToolInput,
) -> dict[str, Any]:
    payload = dict(state.get("tool_input") or {})
    datetime_result: dict[str, Any] | None = None

    if tool_name == "get_current_datetime":
        payload.setdefault("timezone", "Asia/Shanghai")
        if state.get("override_now"):
            payload["override_now"] = state.get("override_now")
        if state.get("fixed_now") and not payload.get("fixed_now"):
            payload["fixed_now"] = state.get("fixed_now")
        payload = validate_tool_input(tool_name, payload)
        payload.update({"query": state.get("question", ""), "user_id": state.get("user_id"), "role": role})
        return payload

    runtime_extras = {key: payload[key] for key in ("file_path",) if key in payload}
    selected_action = str(state.get("selected_action") or "") or None
    normalize_tool_payload_for_action_contract(tool_name, payload, selected_action=selected_action)
    try:
        payload = validate_tool_input(tool_name, payload)
    except ValidationError as exc:
        payload = finalize_tool_input(state, tool_name, payload, datetime_result, str(exc))
        normalize_tool_payload_for_action_contract(tool_name, payload, selected_action=selected_action)
        runtime_extras.update({key: payload[key] for key in ("file_path",) if key in payload})
        payload = validate_tool_input(tool_name, payload)
    payload = prune_tool_payload_for_action_contract(tool_name, payload)
    payload.update(runtime_extras)
    payload.update({"query": state.get("question", ""), "user_id": state.get("user_id"), "role": role})
    return payload
