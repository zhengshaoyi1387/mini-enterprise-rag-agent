from __future__ import annotations

from typing import Any

from mini_rag.capabilities.calendar.resolver import is_unresolved_calendar_event_id
from mini_rag.graph.state import AgentState
from mini_rag.orchestration.completion import check_goal_completion
from mini_rag.orchestration.react_executor import ReActExecutionResult, ReActExecutor
from mini_rag.planning.gates import apply_capability_gates
from mini_rag.security.permissions import normalize_role
from mini_rag.answer.templates import friendly_permission_answer


def apply_goal_aware_completion(
    nodes: Any,
    state: AgentState,
    result: ReActExecutionResult,
    executor: ReActExecutor,
    next_action: Any,
) -> ReActExecutionResult:
    goal_contract = state.get("goal_contract") if isinstance(state.get("goal_contract"), dict) else {}
    if not goal_contract:
        state["completion_check"] = check_goal_completion(state, {}).to_dict()
        return result

    steps = [dict(step) for step in result.steps]
    current_status = result.status
    max_goal_steps = 3
    for iteration in range(1, max_goal_steps + 1):
        check = check_goal_completion(state, goal_contract)
        check_dict = check.to_dict()
        check_dict["iteration"] = iteration
        if state.get("_safe_next_action_triggered"):
            check_dict["safe_next_action_triggered"] = True
            check_dict["safe_next_action_source"] = str(state.get("_safe_next_action_source") or "deterministic")
        state["completion_check"] = check_dict
        state.setdefault("completion_checks", []).append(check_dict)
        state.setdefault("observations", []).append(
            {
                "type": "completion_check",
                "iteration": iteration,
                "status": check.status,
                "goal_type": check.goal_type,
                "reason": check.reason,
                "safe_next_action_source": check_dict.get("safe_next_action_source"),
            }
        )

        if check.status == "completed":
            return ReActExecutionResult(status="success" if current_status == "success" else current_status, steps=tuple(steps), finish_reason=check.reason)
        if check.status == "partial":
            return ReActExecutionResult(status="partial", steps=tuple(steps), finish_reason=check.reason)
        if check.status == "needs_clarification":
            state["intent"] = "need_clarification"
            state["final_answer"] = completion_user_message(check_dict)
            return ReActExecutionResult(status="need_clarification", steps=tuple(steps), finish_reason=check.reason)
        if check.status == "failed":
            state["final_answer"] = completion_user_message(check_dict)
            return ReActExecutionResult(status="failed", steps=tuple(steps), finish_reason=check.reason)

        safe_next = check.safe_next_action if isinstance(check.safe_next_action, dict) else {}
        safe_task = safe_next.get("task") if isinstance(safe_next.get("task"), dict) else {}
        if not safe_task:
            state["final_answer"] = completion_user_message(check_dict)
            return ReActExecutionResult(status="partial", steps=tuple(steps), finish_reason=check.reason)
        safe_task = append_safe_react_task(state, safe_task, iteration=iteration)
        issue = validate_safe_react_task(nodes, state, safe_task)
        if issue:
            state.setdefault("observations", []).append({"type": "safe_next_action", "status": "blocked", **issue})
            state["completion_check"] = {**check_dict, "status": "failed", "reason": "safe_next_action_blocked", "error": issue}
            state["final_answer"] = "目标尚未完成，且补执行动作未通过安全校验，所以不会执行日历写操作。"
            return ReActExecutionResult(status="failed", steps=tuple(steps), finish_reason="safe_next_action_blocked")
        state.setdefault("observations", []).append(
            {
                "type": "safe_next_action",
                "status": "triggered",
                "source": safe_next.get("source") or "deterministic",
                "reason": safe_next.get("reason") or check.reason,
                "task_id": safe_task.get("task_id"),
                "tool_name": safe_task.get("tool_name"),
                "action": safe_task.get("action"),
            }
        )
        state["_safe_next_action_triggered"] = True
        state["_safe_next_action_source"] = str(safe_next.get("source") or "deterministic")
        followup = executor.run(
            state,
            next_action=next_action,
            call_tool=nodes._make_tool_callback(state),
            search_rag=nodes._make_rag_callback(state),
        )
        for step in followup.steps:
            merged_step = dict(step)
            merged_step["step"] = len(steps) + 1
            merged_step["goal_react_iteration"] = iteration
            steps.append(merged_step)
        current_status = followup.status

    state["completion_check"] = {
        **(state.get("completion_check") if isinstance(state.get("completion_check"), dict) else {}),
        "status": "partial",
        "reason": "max_goal_react_steps_reached",
        "max_steps_reached": True,
    }
    state["final_answer"] = "目标尚未确认完成，已达到受控 ReAct 最大步数，未继续执行。"
    return ReActExecutionResult(status="partial", steps=tuple(steps), finish_reason="max_goal_react_steps_reached")


def completion_user_message(completion_check: dict[str, Any]) -> str:
    status = str(completion_check.get("status") or "")
    reason = str(completion_check.get("reason") or "")
    if status == "needs_clarification":
        if reason == "multiple_candidates":
            return "匹配到多个日程，请指定要更新的具体会议 event_id 或标题后再修改。"
        return "目标还不够明确，需要补充信息后才能执行。"
    if reason == "not_found":
        return "没有找到匹配的目标会议，因此没有执行更新。"
    if reason == "updated_field_mismatch":
        return "日程写操作返回结果与目标字段不一致，不能声称更新已完成。"
    if reason == "missing_expected_result":
        return "已找到目标会议，但没有明确要修改的字段，因此不会自动执行更新。"
    return "用户目标尚未确认完成，因此不能声称操作已成功。"


def append_safe_react_task(state: AgentState, task: dict[str, Any], *, iteration: int) -> dict[str, Any]:
    candidate = dict(task)
    existing_ids = {
        str(item.get("task_id") or "")
        for item in (state.get("task_queue") or []) + ((state.get("execution_plan") or {}).get("tasks") or [])
        if isinstance(item, dict)
    }
    base_id = str(candidate.get("task_id") or "goal_react_calendar_update")
    task_id = base_id
    suffix = iteration
    while task_id in existing_ids or task_id in set(state.get("completed_tasks") or []):
        suffix += 1
        task_id = f"{base_id}_{suffix}"
    candidate["task_id"] = task_id
    candidate.setdefault("depends_on", [])
    plan = dict(state.get("execution_plan") or {})
    tasks = [dict(item) for item in (plan.get("tasks") or []) if isinstance(item, dict)]
    tasks.append(candidate)
    plan["tasks"] = tasks
    state["execution_plan"] = plan
    state["task_queue"] = [dict(item) for item in (state.get("task_queue") or []) if isinstance(item, dict)] + [candidate]
    validation = dict(state.get("plan_validation") or {})
    executable = [dict(item) for item in (validation.get("executable_tasks") or []) if isinstance(item, dict)]
    executable.append(candidate)
    validation["executable_tasks"] = executable
    validation.setdefault("validation_status", "valid")
    state["plan_validation"] = validation
    return candidate


def validate_safe_react_task(nodes: Any, state: AgentState, task: dict[str, Any]) -> dict[str, Any] | None:
    role = normalize_role(state.get("role"))
    role_policies = nodes._get_role_policies(state)
    tool = str(task.get("tool") or task.get("tool_name") or "").strip()
    action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").strip().lower()
    if tool != "manage_company_calendar" or action != "update":
        return {"code": "unsupported_safe_next_action", "message": "safe next action only supports calendar update"}
    allowed = nodes.tool_registry.allowed_actions(tool, role, role_policies=role_policies)
    if "*" not in allowed and action not in allowed:
        return {"code": "permission_denied", "message": friendly_permission_answer(role, tool, action)}
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    if is_unresolved_calendar_event_id(tool_input.get("event_id")):
        return {"code": "unresolved_event_id", "message": "safe update requires a concrete event_id"}
    for field in ("date", "start_date", "end_date"):
        value = str(tool_input.get(field) or "").strip()
        if value and not nodes._is_iso_date(value):
            return {"code": "unresolved_date", "field": field, "message": "safe update date must be resolver-produced ISO date"}
    candidate_tasks = [dict(item) for item in (state.get("plan_validation") or {}).get("executable_tasks") or [] if isinstance(item, dict)]
    gated = apply_capability_gates(
        {
            "route": state.get("route"),
            "intent": state.get("intent"),
            "standalone_query": state.get("standalone_query"),
            "execution_plan": {"tasks": candidate_tasks, "strategy": (state.get("execution_plan") or {}).get("strategy", "")},
            "selected_tool": tool,
            "selected_action": action,
            "tool_input": tool_input,
        },
        candidate_tasks,
        role=role,
        tool_registry=nodes.tool_registry,
        role_policies=role_policies,
        state=state,
    )
    if gated is not None:
        return {"code": "capability_gate", "message": str(gated.get("normalization_reason") or "safe update rejected by capability gate")}
    return None


__all__ = ["apply_goal_aware_completion"]
