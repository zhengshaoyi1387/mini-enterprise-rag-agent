from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_rag.capabilities.attendance.validator import validate_attendance_tasks
from mini_rag.capabilities.calendar.validator import (
    calendar_write_needs_clarification,
    validate_calendar_tasks,
)


@dataclass(frozen=True)
class CapabilityGateDecision:
    route: str
    intent: str
    topic: str
    normalization_reason: str
    validation_status: str | None = None
    validation_issues: tuple[dict[str, Any], ...] = ()
    missing_required_slots: tuple[str, ...] = ()

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        updated = dict(payload)
        updated.update(
            {
                "route": self.route,
                "intent": self.intent,
                "selected_tool": None,
                "selected_action": None,
                "tool_input": {},
                "required_tools": [],
                "execution_plan": {"tasks": [], "strategy": ""},
                "topic": self.topic,
                "normalization_reason": self.normalization_reason,
            }
        )
        if self.validation_status:
            updated["validation_status"] = self.validation_status
        if self.validation_issues:
            updated["validation_issues"] = list(self.validation_issues)
        if self.missing_required_slots:
            updated["missing_required_slots"] = list(self.missing_required_slots)
        return updated


def _issue_dict(issue: Any) -> dict[str, Any]:
    return {
        "code": getattr(issue, "code", ""),
        "message": getattr(issue, "message", ""),
        "layer": getattr(issue, "layer", ""),
        "task_id": getattr(issue, "task_id", None),
        "field": getattr(issue, "field", None),
    }


def first_disallowed_tool_task(
    tasks: list[dict[str, Any]],
    role: str,
    *,
    tool_registry: Any,
    role_policies: Any | None = None,
) -> dict[str, Any] | None:
    for task in tasks:
        if not isinstance(task, dict) or str(task.get("kind") or "").lower() != "tool":
            continue
        tool = str(task.get("tool") or "").strip()
        if not tool or not tool_registry.has_tool(tool):
            return task
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        action = str(task.get("action") or tool_input.get("action") or "*").strip().lower() or "*"
        allowed = tool_registry.allowed_actions(tool, role, role_policies=role_policies)
        if "*" not in allowed and action not in allowed:
            return task
    return None


def calendar_write_ability_question_requires_confirmation(
    payload: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    state: dict[str, Any] | None = None,
) -> bool:
    has_calendar_write = any(
        isinstance(task, dict)
        and str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or "") == "manage_company_calendar"
        and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() in {"create", "update", "delete"}
        for task in tasks
    )
    selected_write = (
        str(payload.get("selected_tool") or "") == "manage_company_calendar"
        and str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "").lower()
        in {"create", "update", "delete"}
    )
    if not has_calendar_write and not selected_write:
        return False
    text = "\n".join(
        str(value or "")
        for value in (
            payload.get("standalone_query"),
            (state or {}).get("question"),
            (state or {}).get("standalone_query"),
        )
    )
    has_user_requested_query = any(token in text for token in ("查询", "查一下", "查看")) and any(
        isinstance(task, dict)
        and str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or "") == "manage_company_calendar"
        and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "query"
        for task in tasks
    )
    if has_user_requested_query:
        return False
    if not ("?" in text or "？" in text):
        return False
    ability_markers = ("能不能", "能否", "可不可以", "可以不可以", "是否可以", "可以吗")
    return any(marker in text for marker in ability_markers)


def classification_covers_current_message(classification: dict[str, Any], question: str) -> bool:
    standalone = " ".join(str(classification.get("standalone_query") or "").strip().split())
    original = " ".join(str(question or "").strip().split())
    if not standalone or not original:
        return True
    normalized_standalone = standalone.rstrip("。！？?!；;，,")
    normalized_original = original.rstrip("。！？?!；;，,")
    if normalized_standalone == normalized_original:
        return True
    selected_tool = str(classification.get("selected_tool") or "")
    if selected_tool == "get_current_datetime" and len(normalized_standalone) < len(normalized_original):
        return False
    return len(normalized_standalone) >= max(1, int(len(normalized_original) * 0.85))


def evaluate_capability_gates(
    payload: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    role: str,
    tool_registry: Any,
    role_policies: Any | None = None,
    state: dict[str, Any] | None = None,
) -> CapabilityGateDecision | None:
    previous_context = (state or {}).get("previous_tool_context") if state is not None else {}
    if calendar_write_ability_question_requires_confirmation(payload, tasks, state=state):
        return CapabilityGateDecision(
            route="direct",
            intent="need_clarification",
            topic="calendar_write_confirmation_question",
            normalization_reason="calendar write is phrased as an ability question",
            validation_status="needs_clarification",
        )
    allowed_calendar_actions = tool_registry.allowed_actions(
        "manage_company_calendar",
        role,
        role_policies=role_policies,
    )
    if calendar_write_needs_clarification(
        payload,
        tasks,
        previous_tool_context=previous_context if isinstance(previous_context, dict) else {},
        allowed_actions=allowed_calendar_actions,
    ):
        return CapabilityGateDecision(
            route="direct",
            intent="need_clarification",
            topic="calendar_write_clarification",
            normalization_reason="calendar write target unresolved",
        )

    disallowed_task = first_disallowed_tool_task(
        tasks,
        role,
        tool_registry=tool_registry,
        role_policies=role_policies,
    )
    if disallowed_task is not None:
        tool = str(disallowed_task.get("tool") or "")
        action = str(disallowed_task.get("action") or (disallowed_task.get("tool_input") or {}).get("action") or "*")
        return CapabilityGateDecision(
            route="direct",
            intent="permission_required",
            topic=f"{tool}.{action}.permission_required",
            normalization_reason="task action not visible",
            validation_status="refused",
        )

    attendance_validation = validate_attendance_tasks(tasks, role=role)
    if attendance_validation.status != "valid":
        return CapabilityGateDecision(
            route="direct",
            intent="permission_required" if attendance_validation.status == "refused" else attendance_validation.status,
            topic="attendance.permission_required",
            normalization_reason=attendance_validation.reason or "attendance capability validation failed",
            validation_status=attendance_validation.status,
            validation_issues=tuple(_issue_dict(issue) for issue in attendance_validation.issues),
        )

    calendar_validation = validate_calendar_tasks(tasks)
    if calendar_validation.status != "valid":
        missing_slots = tuple(issue.field for issue in calendar_validation.issues if issue.field)
        return CapabilityGateDecision(
            route="direct",
            intent="need_clarification" if calendar_validation.status == "needs_clarification" else calendar_validation.status,
            topic="calendar_validation",
            normalization_reason=calendar_validation.reason or "calendar capability validation failed",
            validation_status=calendar_validation.status,
            validation_issues=tuple(_issue_dict(issue) for issue in calendar_validation.issues),
            missing_required_slots=missing_slots,
        )

    return None


def apply_capability_gates(
    payload: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    role: str,
    tool_registry: Any,
    role_policies: Any | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    decision = evaluate_capability_gates(
        payload,
        tasks,
        role=role,
        tool_registry=tool_registry,
        role_policies=role_policies,
        state=state,
    )
    if decision is None:
        return None
    return decision.apply(payload)
