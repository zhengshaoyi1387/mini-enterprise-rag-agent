from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_rag.planning.goal_extractor import Goal

TERMINAL_STATUSES = {"ok", "empty", "no_evidence", "skipped", "needs_clarification", "refused", "blocked"}


@dataclass(frozen=True)
class GoalCoverageReport:
    ready_to_answer: bool
    covered_goal_ids: tuple[str, ...] = ()
    missing_goal_ids: tuple[str, ...] = ()
    unsupported_goal_ids: tuple[str, ...] = ()
    is_mixed_task: bool = False
    should_use_rag: bool = False
    reason: str = ""


def _results_by_task_id(task_results: list[dict[str, Any]] | None, rag_results: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in list(task_results or []) + list(rag_results or []):
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "").strip()
        if task_id:
            out[task_id] = item
    return out


def _has_any_rag_result(task_results: list[dict[str, Any]] | None, rag_results: list[dict[str, Any]] | None) -> bool:
    for item in list(task_results or []) + list(rag_results or []):
        if isinstance(item, dict) and str(item.get("kind") or "").lower() == "rag":
            return True
    return False


def _status_is_terminal(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    status = str(result.get("status") or "").strip().lower()
    if not status:
        return bool(result)
    return status in TERMINAL_STATUSES


def check_goal_coverage(
    goals: tuple[Goal, ...] | list[Goal],
    *,
    execution_plan: dict[str, Any] | None,
    task_results: list[dict[str, Any]] | None,
    rag_results: list[dict[str, Any]] | None = None,
) -> GoalCoverageReport:
    """Check whether approved goals have corresponding terminal results."""

    del execution_plan
    goals = tuple(goals or ())
    is_mixed = any(goal.capability == "mixed_task" for goal in goals) or (
        any(goal.capability == "rag_qa" for goal in goals)
        and any(goal.capability not in {"rag_qa", "mixed_task", "direct"} for goal in goals)
    )
    should_use_rag = any(goal.capability == "rag_qa" for goal in goals)
    by_task = _results_by_task_id(task_results, rag_results)
    if should_use_rag and not _has_any_rag_result(task_results, rag_results):
        covered_non_rag = tuple(
            goal.goal_id
            for goal in goals
            if goal.capability not in {"rag_qa", "mixed_task"} and _status_is_terminal(by_task.get(goal.goal_id))
        )
        missing_rag = tuple(goal.goal_id for goal in goals if goal.capability == "rag_qa") or ("rag_qa",)
        return GoalCoverageReport(
            ready_to_answer=False,
            covered_goal_ids=covered_non_rag,
            missing_goal_ids=missing_rag,
            is_mixed_task=is_mixed,
            should_use_rag=True,
            reason="rag goal required but no rag task/result is present",
        )

    covered: list[str] = []
    missing: list[str] = []
    unsupported: list[str] = []
    for goal in goals:
        if goal.capability == "mixed_task":
            continue
        result = by_task.get(goal.goal_id)
        if _status_is_terminal(result):
            covered.append(goal.goal_id)
            if str((result or {}).get("status") or "").lower() in {"empty", "no_evidence", "skipped"}:
                unsupported.append(goal.goal_id)
        else:
            missing.append(goal.goal_id)

    ready = not missing
    return GoalCoverageReport(
        ready_to_answer=ready,
        covered_goal_ids=tuple(covered),
        missing_goal_ids=tuple(missing),
        unsupported_goal_ids=tuple(unsupported),
        is_mixed_task=is_mixed,
        should_use_rag=should_use_rag,
        reason="all goals covered" if ready else "some goals missing terminal results",
    )
