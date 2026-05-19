from __future__ import annotations

import re
from typing import Any, Iterable

from mini_rag.core.contracts import ValidationIssue, ValidationResult
from mini_rag.capabilities.datetime.resolver import normalize_time_requirement
from mini_rag.capabilities.calendar.resolver import is_unresolved_calendar_event_id

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _calendar_action(task: dict[str, Any]) -> str:
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    return str(task.get("action") or tool_input.get("action") or "query").strip().lower() or "query"


def _has_query_source(tasks: list[dict[str, Any]], index: int) -> bool:
    for candidate in tasks[:index]:
        if str(candidate.get("kind") or "").lower() != "tool":
            continue
        if str(candidate.get("tool") or "") != "manage_company_calendar":
            continue
        if _calendar_action(candidate) == "query":
            return True
    return False


def _date_is_resolvable(task: dict[str, Any]) -> bool:
    time_requirement = normalize_time_requirement(task.get("time_requirement") if isinstance(task.get("time_requirement"), dict) else {})
    return bool(
        time_requirement.get("requires_current_datetime")
        or time_requirement.get("absolute_date")
        or time_requirement.get("date_range")
    )


def _validate_date_fields(task: dict[str, Any], fields: tuple[str, ...]) -> list[ValidationIssue]:
    payload = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    issues: list[ValidationIssue] = []
    for field in fields:
        value = str(payload.get(field) or "").strip()
        if not value:
            continue
        if not DATE_RE.fullmatch(value):
            issues.append(
                ValidationIssue(
                    code="calendar_symbolic_date",
                    field=field,
                    task_id=str(task.get("task_id") or "") or None,
                    layer="validator",
                    message="Calendar date fields must be resolved to YYYY-MM-DD before real tools.",
                )
            )
    return issues


def validate_calendar_tasks(tasks: list[dict[str, Any]]) -> ValidationResult:
    """Validate calendar tasks at the executable-plan boundary.

    This is intentionally generic capability validation. It does not inspect
    user-question keywords; it only checks structured task contracts.
    """

    issues: list[ValidationIssue] = []
    for index, task in enumerate(tasks):
        if str(task.get("kind") or "").lower() != "tool" or str(task.get("tool") or "") != "manage_company_calendar":
            continue
        payload = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        action = _calendar_action(task)
        task_id = str(task.get("task_id") or "") or None

        if action == "query":
            issues.extend(_validate_date_fields(task, ("start_date", "end_date")))
            continue

        if action == "create":
            missing = [field for field in ("title", "date", "time") if not str(payload.get(field) or "").strip()]
            if "date" in missing and _date_is_resolvable(task):
                missing.remove("date")
            if missing:
                issues.append(
                    ValidationIssue(
                        code="calendar_create_missing_required_slots",
                        task_id=task_id,
                        field=",".join(missing),
                        layer="validator",
                        message="Calendar create requires title, date, and time before writing.",
                    )
                )
            issues.extend(_validate_date_fields(task, ("date",)))
            continue

        if action in {"update", "delete"}:
            event_id = payload.get("event_id")
            has_selector = any(isinstance(payload.get(key), dict) for key in ("selector", "event_selector", "target", "match"))
            if is_unresolved_calendar_event_id(event_id) and not has_selector and not _has_query_source(tasks, index):
                issues.append(
                    ValidationIssue(
                        code=f"calendar_{action}_missing_event_id",
                        task_id=task_id,
                        field="event_id",
                        layer="validator",
                        message=f"Calendar {action} requires a concrete event_id or a prior query resolution step.",
                    )
                )
            if action == "update":
                issues.extend(_validate_date_fields(task, ("date",)))

    if issues:
        return ValidationResult(status="needs_clarification", issues=tuple(issues), reason=issues[0].message)
    return ValidationResult(status="valid")


def has_executable_calendar_query_source(tasks: list[dict[str, Any]]) -> bool:
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if str(task.get("kind") or "").lower() != "tool" or str(task.get("tool") or "") != "manage_company_calendar":
            continue
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        action = str(task.get("action") or tool_input.get("action") or "").lower()
        if action != "query":
            continue
        time_requirement = normalize_time_requirement(task.get("time_requirement") if isinstance(task.get("time_requirement"), dict) else {})
        if time_requirement.get("requires_current_datetime") or time_requirement.get("absolute_date") or time_requirement.get("date_range"):
            return True
        start = str(tool_input.get("start_date") or "").strip()
        end = str(tool_input.get("end_date") or "").strip()
        if DATE_RE.fullmatch(start) and DATE_RE.fullmatch(end):
            return True
    return False


def calendar_write_needs_clarification(
    payload: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    previous_tool_context: dict[str, Any] | None = None,
    allowed_actions: Iterable[str] = (),
) -> bool:
    """Return whether a calendar write intent lacks a resolvable target.

    Permission denial is handled by the permission validator, so this function
    returns False when the caller's allowed actions do not include the write
    action. That keeps "refused" and "needs clarification" separate.
    """

    allowed = {str(action).lower() for action in allowed_actions}
    write_tasks = [
        task
        for task in tasks
        if isinstance(task, dict)
        and str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or "") == "manage_company_calendar"
        and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() in {"update", "delete"}
    ]
    previous_context = previous_tool_context if isinstance(previous_tool_context, dict) else {}
    has_previous_events = bool(previous_context.get("events"))

    selected_tool = str(payload.get("selected_tool") or "").strip()
    selected_action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "").strip().lower()
    selected_write_intent = selected_tool == "manage_company_calendar" and selected_action in {"update", "delete"}
    if selected_write_intent and "*" not in allowed and selected_action not in allowed:
        return False
    for task in write_tasks:
        action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").strip().lower()
        if action in {"update", "delete"} and "*" not in allowed and action not in allowed:
            return False

    if selected_write_intent and not write_tasks:
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        if is_unresolved_calendar_event_id(tool_input.get("event_id")) and not has_executable_calendar_query_source(tasks):
            return True
    if not write_tasks:
        return False
    if has_previous_events:
        return False

    for task in write_tasks:
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        if not is_unresolved_calendar_event_id(tool_input.get("event_id")):
            continue
        if has_executable_calendar_query_source(tasks):
            continue
        return True
    return False
