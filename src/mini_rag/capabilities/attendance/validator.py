from __future__ import annotations

from typing import Any

from mini_rag.core.contracts import ValidationIssue, ValidationResult
from mini_rag.security.permissions import normalize_role


FULL_ATTENDANCE_ROLES = {"hr", "admin"}
LIMITED_ATTENDANCE_ROLES = {"employee", "user"}


def validate_attendance_tasks(tasks: list[dict[str, Any]], *, role: str | None) -> ValidationResult:
    """Validate attendance data access beyond coarse tool visibility.

    The tool permission matrix says whether a role may use the attendance
    capability at all. This validator enforces row/detail scope: ordinary
    employees may request a named personal record, but department/all-employee
    detail queries require HR/admin privileges.
    """

    normalized_role = normalize_role(role)
    if normalized_role in FULL_ATTENDANCE_ROLES:
        return ValidationResult(status="valid")

    for task in tasks:
        if not isinstance(task, dict) or str(task.get("kind") or "").lower() != "tool":
            continue
        if str(task.get("tool") or "") != "query_attendance_summary":
            continue
        issue = _attendance_scope_issue(task, normalized_role)
        if issue is not None:
            return ValidationResult(
                status="refused",
                issues=(issue,),
                reason="attendance data scope requires HR/admin role",
            )
    return ValidationResult(status="valid")


def _attendance_scope_issue(task: dict[str, Any], role: str) -> ValidationIssue | None:
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    if role not in LIMITED_ATTENDANCE_ROLES:
        return ValidationIssue(
            code="attendance_role_not_allowed",
            message="当前角色无权查看考勤数据。",
            layer="validator",
            task_id=str(task.get("task_id") or "") or None,
            field="role",
        )

    employee_name = str(tool_input.get("employee_name") or "").strip()
    if employee_name:
        return None

    department = str(tool_input.get("department") or "all").strip() or "all"
    group_by = str(tool_input.get("group_by") or "").strip().lower()
    include_records = bool(tool_input.get("include_records"))
    status_filters = tool_input.get("status_filters")
    status_filter = str(tool_input.get("status_filter") or "").strip()
    has_status_filter = bool(status_filter or (isinstance(status_filters, list) and status_filters) or isinstance(status_filters, str))
    objective = str(task.get("objective") or task.get("query") or "")

    broad_department = department not in {"", "all"}
    employee_grouping = group_by == "employee"
    explicit_detail = include_records or "明细" in objective or "完整" in objective
    anomaly_without_person = has_status_filter and any(token in objective for token in ("异常", "迟到", "缺勤", "请假"))

    if broad_department or employee_grouping or explicit_detail or anomaly_without_person:
        return ValidationIssue(
            code="attendance_scope_requires_hr",
            message="普通员工无权查看部门或全员考勤明细。",
            layer="validator",
            task_id=str(task.get("task_id") or "") or None,
            field="attendance_scope",
        )
    return None
