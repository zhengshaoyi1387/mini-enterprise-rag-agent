from __future__ import annotations

from typing import Any


def _ensure_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        value = {}
        state[key] = value
    return value


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _set_missing(target: dict[str, Any], values: dict[str, Any]) -> None:
    for key, value in values.items():
        if _present(value) and not _present(target.get(key)):
            target[key] = value


def get_runtime_context(state: dict[str, Any]) -> dict[str, Any]:
    runtime = _ensure_dict(state, "runtime_context")
    permissions = state.get("permissions") if isinstance(state.get("permissions"), dict) else {}
    _set_missing(
        runtime,
        {
            "user_id": state.get("user_id"),
            "role": state.get("role") or permissions.get("role"),
            "permissions": permissions,
            "allowed_kbs": state.get("allowed_kbs"),
            "requested_kbs": state.get("requested_kbs"),
            "time_context_result": state.get("time_context_result"),
            "capability_catalog": state.get("capability_catalog"),
            "session_id": state.get("session_id"),
            "workflow_run_id": state.get("workflow_run_id"),
        },
    )
    return runtime


def get_plan_state(state: dict[str, Any]) -> dict[str, Any]:
    plan_state = _ensure_dict(state, "plan_state")
    raw_plan = state.get("raw_plan") if isinstance(state.get("raw_plan"), dict) else {}
    validation = state.get("plan_validation") if isinstance(state.get("plan_validation"), dict) else {}
    _set_missing(
        plan_state,
        {
            "overall_intent": raw_plan.get("overall_intent") or state.get("intent"),
            "route": state.get("route"),
            "intent": state.get("intent"),
            "execution_plan": state.get("execution_plan"),
            "resolved_time_facts": state.get("resolved_time_facts"),
            "plan_validation": validation,
            "executable_tasks": validation.get("executable_tasks"),
            "blocked_tasks": validation.get("blocked_tasks"),
            "clarification_tasks": validation.get("clarification_tasks"),
        },
    )
    return plan_state


def get_execution_state(state: dict[str, Any]) -> dict[str, Any]:
    execution_state = _ensure_dict(state, "execution_state")
    _set_missing(
        execution_state,
        {
            "react_status": state.get("react_status"),
            "react_steps": state.get("react_steps"),
            "observations": state.get("observations"),
            "tool_calls": state.get("tool_calls"),
            "task_results": state.get("task_results"),
            "completed_tasks": state.get("completed_tasks"),
            "current_tool_context": state.get("current_tool_context"),
            "previous_tool_context": state.get("previous_tool_context"),
        },
    )
    return execution_state


def get_answer_state(state: dict[str, Any]) -> dict[str, Any]:
    answer_state = _ensure_dict(state, "answer_state")
    _set_missing(
        answer_state,
        {
            "answer_policy": state.get("answer_policy"),
            "answer_packet": state.get("answer_packet"),
            "evidence_assessment": state.get("evidence_assessment") or state.get("rag_answerability"),
            "completion_assessment": state.get("completion_assessment"),
            "sources": state.get("sources"),
            "candidate_sources": state.get("candidate_sources"),
            "final_answer": state.get("final_answer") or state.get("answer"),
            "answer": state.get("answer") or state.get("final_answer"),
        },
    )
    return answer_state


def _remaining_executable_tasks(plan: dict[str, Any], completed: set[str]) -> list[dict[str, Any]]:
    tasks = [task for task in (plan.get("tasks") or []) if isinstance(task, dict)]
    remaining: list[dict[str, Any]] = []
    for task in tasks:
        if str(task.get("kind") or "").lower() not in {"tool", "rag"}:
            continue
        task_id = str(task.get("task_id") or task.get("id") or "").strip()
        if task_id and task_id in completed:
            continue
        remaining.append(task)
    return remaining


def _normalize_completion_assessment(state: dict[str, Any]) -> None:
    answer_state = _ensure_dict(state, "answer_state")
    completion = answer_state.get("completion_assessment")
    if not isinstance(completion, dict):
        completion = state.get("completion_assessment") if isinstance(state.get("completion_assessment"), dict) else {}
    completion = dict(completion)
    execution_status = str(completion.get("execution_status") or "")
    if execution_status in {"need_clarification", "blocked", "failed", "error", "refused"}:
        completion["ready_to_answer"] = False
    elif execution_status in {"success", "partial"}:
        completion["ready_to_answer"] = True
    answer_state["completion_assessment"] = completion
    state["completion_assessment"] = completion


def sync_legacy_state_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Synchronize top-level compatibility fields with standardized state areas.

    The four state areas are the canonical shape for new code. Top-level fields
    remain as a facade for legacy tests, trace consumers, and scripts.
    """

    runtime = get_runtime_context(state)
    plan = get_plan_state(state)
    execution = get_execution_state(state)
    answer = get_answer_state(state)

    for key in ("user_id", "role", "allowed_kbs", "requested_kbs", "time_context_result", "capability_catalog", "permissions"):
        if _present(runtime.get(key)):
            state[key] = runtime.get(key)

    for key in ("route", "intent", "execution_plan", "resolved_time_facts", "plan_validation"):
        if _present(plan.get(key)):
            state[key] = plan.get(key)
    validation = state.get("plan_validation") if isinstance(state.get("plan_validation"), dict) else {}
    for key in ("executable_tasks", "blocked_tasks", "clarification_tasks"):
        if _present(plan.get(key)):
            validation[key] = plan.get(key)
        elif _present(validation.get(key)):
            plan[key] = validation.get(key)
    if validation:
        state["plan_validation"] = validation
        plan["plan_validation"] = validation

    completed = {str(item) for item in (execution.get("completed_tasks") or state.get("completed_tasks") or [])}
    plan_for_remaining = plan.get("execution_plan") if isinstance(plan.get("execution_plan"), dict) else state.get("execution_plan") or {}
    if execution.get("react_status") == "success" and _remaining_executable_tasks(plan_for_remaining, completed):
        execution["react_status"] = "partial"
    for key in ("react_status", "react_steps", "observations", "tool_calls", "task_results", "completed_tasks", "current_tool_context", "previous_tool_context"):
        if _present(execution.get(key)):
            state[key] = execution.get(key)

    for key in ("answer_policy", "answer_packet", "evidence_assessment", "completion_assessment", "sources", "candidate_sources"):
        if _present(answer.get(key)):
            state[key] = answer.get(key)
    final_answer = answer.get("final_answer") or answer.get("answer")
    if _present(final_answer):
        state["final_answer"] = final_answer
        state["answer"] = final_answer
        answer["final_answer"] = final_answer
        answer["answer"] = final_answer

    _normalize_completion_assessment(state)
    return state


def refresh_state_views(state: dict[str, Any]) -> dict[str, Any]:
    """Rebuild state views from current top-level fields, then sync facade keys."""

    runtime = _ensure_dict(state, "runtime_context")
    runtime.update(
        {
            "user_id": state.get("user_id"),
            "role": state.get("role"),
            "permissions": state.get("permissions") if isinstance(state.get("permissions"), dict) else {},
            "allowed_kbs": state.get("allowed_kbs"),
            "requested_kbs": state.get("requested_kbs"),
            "time_context_result": state.get("time_context_result"),
            "capability_catalog": state.get("capability_catalog"),
            "session_id": state.get("session_id"),
            "workflow_run_id": state.get("workflow_run_id"),
        }
    )
    validation = state.get("plan_validation") if isinstance(state.get("plan_validation"), dict) else {}
    raw_plan = state.get("raw_plan") if isinstance(state.get("raw_plan"), dict) else {}
    plan = _ensure_dict(state, "plan_state")
    existing_overall = plan.get("overall_intent")
    plan.update(
        {
            "overall_intent": raw_plan.get("overall_intent") or existing_overall or state.get("intent"),
            "route": state.get("route"),
            "intent": state.get("intent"),
            "execution_plan": state.get("execution_plan"),
            "resolved_time_facts": state.get("resolved_time_facts"),
            "plan_validation": validation,
            "executable_tasks": validation.get("executable_tasks") or plan.get("executable_tasks") or [],
            "blocked_tasks": validation.get("blocked_tasks") or plan.get("blocked_tasks") or [],
            "clarification_tasks": validation.get("clarification_tasks") or plan.get("clarification_tasks") or [],
        }
    )
    execution = _ensure_dict(state, "execution_state")
    execution.update(
        {
            "react_status": state.get("react_status"),
            "react_steps": state.get("react_steps") or [],
            "observations": state.get("observations") or [],
            "tool_calls": state.get("tool_calls") or [],
            "task_results": state.get("task_results") or [],
            "completed_tasks": state.get("completed_tasks") or [],
            "current_tool_context": state.get("current_tool_context") or {},
            "previous_tool_context": state.get("previous_tool_context") or {},
        }
    )
    answer = _ensure_dict(state, "answer_state")
    answer.update(
        {
            "answer_policy": state.get("answer_policy") or {},
            "answer_packet": state.get("answer_packet") or {},
            "evidence_assessment": state.get("evidence_assessment") or state.get("rag_answerability") or {},
            "completion_assessment": state.get("completion_assessment") or {},
            "sources": state.get("sources") or [],
            "candidate_sources": state.get("candidate_sources") or [],
            "final_answer": state.get("final_answer") or state.get("answer") or "",
            "answer": state.get("answer") or state.get("final_answer") or "",
        }
    )
    return sync_legacy_state_fields(state)


__all__ = [
    "get_runtime_context",
    "get_plan_state",
    "get_execution_state",
    "get_answer_state",
    "refresh_state_views",
    "sync_legacy_state_fields",
]
