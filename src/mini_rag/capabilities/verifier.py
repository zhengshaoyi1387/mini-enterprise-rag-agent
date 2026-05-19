from __future__ import annotations

from typing import Any

from mini_rag.capabilities.attendance.resolver import canonical_status_filter_set
from mini_rag.capabilities.attendance.verifier import verify_attendance_result
from mini_rag.capabilities.calendar.verifier import verify_calendar_result
from mini_rag.capabilities.datetime.verifier import verify_datetime_result
from mini_rag.execution.tool_input import verify_tool_result_consistency


def verify_domain_tool_result(tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
    if tool_name == "manage_company_calendar":
        verify_calendar_result(payload, result)
        return
    if tool_name == "query_attendance_summary":
        verify_attendance_result(payload, result)
        return
    if tool_name == "get_current_datetime":
        verify_datetime_result(payload, result)
        return
    verify_tool_result_consistency(tool_name, payload, result)


def task_result_quality_issues(plan_tasks: list[dict[str, Any]], task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return task results that violate the execution/result contract."""

    by_id = {str(result.get("task_id") or ""): result for result in task_results if isinstance(result, dict)}
    issues: list[dict[str, Any]] = []
    bad_statuses = {"error", "failed", "skipped", "needs_clarification", "blocked"}

    for result in task_results:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status") or "").lower()
        tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
        if status in bad_statuses or bool(tool_result.get("error")):
            issues.append(result)

    for task in plan_tasks:
        if not isinstance(task, dict):
            continue
        if str(task.get("kind") or "").lower() != "tool":
            continue
        tool = str(task.get("tool") or "")
        action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower()
        task_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        result = by_id.get(str(task.get("task_id") or ""))
        result_input = result.get("tool_input") if isinstance(result, dict) and isinstance(result.get("tool_input"), dict) else {}
        if tool == "manage_company_calendar" and action == "query":
            planned_event_type = str(task_input.get("event_type") or "").strip()
            actual_event_type = str(result_input.get("event_type") or "").strip()
            if planned_event_type and actual_event_type and planned_event_type != actual_event_type:
                issues.append(
                    {
                        "task_id": task.get("task_id"),
                        "status": "contract_mismatch",
                        "field": "event_type",
                        "planned": planned_event_type,
                        "actual": actual_event_type,
                    }
                )
        if tool == "query_attendance_summary":
            planned_status = canonical_status_filter_set(task_input)
            actual_status = canonical_status_filter_set(result_input)
            if planned_status and actual_status and planned_status != actual_status:
                issues.append(
                    {
                        "task_id": task.get("task_id"),
                        "status": "contract_mismatch",
                        "field": "status_filters",
                        "planned": sorted(planned_status),
                        "actual": sorted(actual_status),
                    }
                )
        if tool != "manage_company_calendar" or action not in {"create", "update", "delete"}:
            continue
        if not result:
            issues.append({"task_id": task.get("task_id"), "status": "missing_result", "objective": task.get("objective")})
            continue
        tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
        expected_status = {"create": "created", "update": "updated", "delete": "deleted"}[action]
        if str(tool_result.get("status") or "").lower() != expected_status:
            issues.append(result)
    return issues


def terminal_tool_results_require_answer(results: list[dict[str, Any]]) -> bool:
    terminal_statuses = {"needs_clarification", "blocked"}
    terminal_errors = {"event not found", "tool_input_validation_failed", "invalid date format", "permission denied"}
    if not results:
        return False
    for result in results:
        if not isinstance(result, dict):
            return False
        status = str(result.get("status") or "").lower()
        tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
        tool_status = str(tool_result.get("status") or "").lower()
        tool_error = str(tool_result.get("error") or "").lower()
        if tool_error in terminal_errors:
            continue
        if status not in terminal_statuses and tool_status not in terminal_statuses:
            return False
        if tool_result.get("error"):
            return False
    return True
