from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from mini_rag.security.permissions import assert_tool_action_permission, normalize_role

BuildPayload = Callable[[dict[str, Any], str, str], dict[str, Any]]
VerifyToolResult = Callable[[str, dict[str, Any], dict[str, Any]], None]
BuildToolContext = Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]
RecordTaskResult = Callable[[dict[str, Any], int], None]


def execute_selected_tool(
    state: dict[str, Any],
    *,
    tool_registry: Any,
    role_policies: Any | None,
    build_payload: BuildPayload,
    verify_tool_result: VerifyToolResult,
    build_current_tool_context: BuildToolContext,
    record_tool_task_result: RecordTaskResult,
    friendly_tool_error: Callable[..., str],
    friendly_tool_validation_error: Callable[[str, ValidationError], str],
    friendly_permission_answer: Callable[[str, str, str | None], str],
) -> dict[str, Any]:
    """Execute the selected tool through schema, permission, and result gates."""

    role = normalize_role(state.get("role"))
    tool_name = str(state.get("selected_tool") or (state.get("required_tools") or [None])[0] or "")
    before_tool_calls = len(state.get("tool_calls") or [])

    if not tool_name:
        state["route"] = "reject"
        state["error"] = "No tool selected"
        state["final_answer"] = "没有识别到可执行的企业能力。"
        state["tool_result"] = {"error": "no tool selected"}
        record_tool_task_result(state, before_tool_calls)
        return state

    if not tool_registry.has_tool(tool_name):
        state["error"] = f"Unknown tool: {tool_name}"
        state["final_answer"] = "没有识别到可执行的企业能力。"
        state["tool_result"] = {"error": "unknown tool", "tool_name": tool_name}
        state.setdefault("tool_calls", []).append({"tool_name": tool_name, "ok": False, "reason": "unknown tool"})
        state.setdefault("audit_events", []).append(
            {"event": "tool_call", "tool_name": tool_name, "role": role, "decision": "blocked", "reason": "unknown tool"}
        )
        record_tool_task_result(state, before_tool_calls)
        return state

    try:
        payload = build_payload(state, tool_name, role)
        action = str(state.get("selected_action") or payload.get("action") or "*").strip().lower() or "*"
        assert_tool_action_permission(role, tool_name, action, role_policies=role_policies)
        cached_datetime = state.get("time_context_result") if tool_name == "get_current_datetime" else None
        if isinstance(cached_datetime, dict) and cached_datetime.get("current_date"):
            result = dict(cached_datetime)
            result["_time_context_cache_hit"] = True
        else:
            result = tool_registry.invoke(tool_name, payload)
        if isinstance(result, dict):
            result = dict(result)
            result.setdefault("tool_name", tool_name)
        else:
            result = {"tool_name": tool_name, "result": result}
        if tool_name == "get_current_datetime":
            state["time_context_payload"] = dict(payload)
            state["time_context_result"] = {key: value for key, value in result.items() if key != "_time_context_cache_hit"}
        verify_tool_result(tool_name, payload, result)
        state["tool_input"] = payload
        state["tool_result"] = result
        if result.get("error"):
            state["final_answer"] = friendly_tool_error(tool_name, result, role=role, action=action)
        else:
            current_context = build_current_tool_context(tool_name, payload, result)
            current_context["trace_id"] = state.get("trace_id")
            state["current_tool_context"] = current_context
            state["final_answer"] = ""
        state.setdefault("tool_calls", []).append(
            {
                "tool_name": tool_name,
                "action": action,
                "args": payload,
                "ok": not bool(result.get("error")),
                "risk_level": result.get("risk_level", "low"),
                "error": result.get("error"),
            }
        )
        state.setdefault("observations", []).append({"type": "tool", "tool_name": tool_name, "result": result})
        state.setdefault("audit_events", []).append(
            {
                "event": "tool_call",
                "tool_name": tool_name,
                "role": role,
                "decision": "blocked" if result.get("error") == "permission denied" else "allowed",
                "action": action,
                "reason": result.get("error"),
            }
        )
    except PermissionError as exc:
        action = str(state.get("selected_action") or (state.get("tool_input") or {}).get("action") or "*")
        state["route"] = "direct"
        state["intent"] = "permission_required"
        state["error"] = str(exc)
        state["final_answer"] = friendly_permission_answer(role, tool_name, action)
        state.setdefault("tool_calls", []).append({"tool_name": tool_name, "action": action, "ok": False, "reason": "permission denied"})
        state.setdefault("audit_events", []).append(
            {"event": "tool_call", "tool_name": tool_name, "action": action, "role": role, "decision": "blocked", "reason": str(exc)}
        )
    except ValidationError as exc:
        state["final_answer"] = friendly_tool_validation_error(tool_name, exc)
        state["tool_result"] = {
            "error": "tool_input_validation_failed",
            "message": str(exc),
            "tool_name": tool_name,
        }
        state.setdefault("tool_calls", []).append(
            {"tool_name": tool_name, "ok": False, "reason": "tool_input_validation_failed", "validation_error": str(exc)}
        )
        state.setdefault("audit_events", []).append(
            {"event": "tool_call", "tool_name": tool_name, "role": role, "decision": "blocked", "reason": "tool_input_validation_failed"}
        )

    record_tool_task_result(state, before_tool_calls)
    return state
