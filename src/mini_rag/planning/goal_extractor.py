from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Goal:
    goal_id: str
    capability: str
    objective: str
    condition: str = ""
    required_result: str = ""
    task: dict[str, Any] = field(default_factory=dict)


def _tasks_from_plan(execution_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    plan = execution_plan if isinstance(execution_plan, dict) else {}
    tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    return [dict(task) for task in tasks if isinstance(task, dict)]


def _tool_capability(task: dict[str, Any]) -> str:
    tool = str(task.get("tool") or task.get("tool_name") or "").strip()
    action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").strip().lower()
    if tool == "get_current_datetime":
        return "datetime"
    if tool == "manage_company_calendar":
        return "calendar_write" if action in {"create", "update", "delete"} else "calendar_query"
    if tool == "query_attendance_summary":
        return "attendance_query"
    if tool == "search_knowledge_base":
        return "rag_qa"
    return "tool"


def _required_result(capability: str, task: dict[str, Any]) -> str:
    if capability == "rag_qa":
        return "grounded_evidence_or_no_evidence"
    if capability == "calendar_write":
        action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "write").strip().lower()
        return f"verified_calendar_{action}_result"
    if capability in {"calendar_query", "attendance_query", "datetime"}:
        return f"{capability}_result"
    return "task_result"


def extract_goals(
    question: str,
    classification: dict[str, Any] | None,
    execution_plan: dict[str, Any] | None,
) -> tuple[Goal, ...]:
    """Extract execution goals from structured classifier and plan output.

    This intentionally prefers already-approved structured plan data over
    natural-language keywords. It is a coverage contract for downstream
    execution, not a business-rule parser.
    """

    classification = classification if isinstance(classification, dict) else {}
    tasks = _tasks_from_plan(execution_plan)
    goals: list[Goal] = []
    seen_ids: set[str] = set()

    for idx, task in enumerate(tasks, start=1):
        kind = str(task.get("kind") or "").strip().lower()
        if kind not in {"tool", "rag", "direct"}:
            continue
        capability = "rag_qa" if kind == "rag" else _tool_capability(task) if kind == "tool" else "direct"
        goal_id = str(task.get("task_id") or capability or f"g{idx}")
        if goal_id in seen_ids:
            goal_id = f"{goal_id}_{idx}"
        seen_ids.add(goal_id)
        objective = str(task.get("objective") or task.get("query") or question).strip() or question
        goals.append(
            Goal(
                goal_id=goal_id,
                capability=capability,
                objective=objective,
                condition=str(task.get("condition") or ""),
                required_result=_required_result(capability, task),
                task=task,
            )
        )

    knowledge_requirement = classification.get("knowledge_requirement")
    knowledge_requirement = knowledge_requirement if isinstance(knowledge_requirement, dict) else {}
    should_use_rag = bool(knowledge_requirement.get("should_use_rag"))
    has_rag_goal = any(goal.capability == "rag_qa" for goal in goals)
    has_tool_goal = any(goal.capability not in {"rag_qa", "direct"} for goal in goals)
    if should_use_rag and not has_rag_goal:
        goals.append(
            Goal(
                goal_id="rag_qa",
                capability="rag_qa",
                objective=str(classification.get("standalone_query") or question).strip() or question,
                required_result="grounded_evidence_or_no_evidence",
                task={"task_id": "rag_qa", "kind": "rag", "query": str(classification.get("standalone_query") or question)},
            )
        )
        has_rag_goal = True

    if has_tool_goal and has_rag_goal:
        goals.append(
            Goal(
                goal_id="mixed_task",
                capability="mixed_task",
                objective=str(classification.get("standalone_query") or question).strip() or question,
                required_result="tool_and_rag_results",
            )
        )

    return tuple(goals)
