from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable


class ReActGuardrailViolation(RuntimeError):
    """Raised when a proposed action violates executor-level safety rules."""


NextAction = Callable[[dict[str, Any], int, list[dict[str, Any]]], dict[str, Any]]
CallTool = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
SearchRAG = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ReActExecutionResult:
    status: str
    steps: tuple[dict[str, Any], ...]
    finish_reason: str = ""


def _task_id(task: dict[str, Any]) -> str:
    return str(task.get("task_id") or task.get("id") or "").strip()


def _compact_raw_result(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"value": str(raw)[:500]}
    output: dict[str, Any] = {}
    for key in ("status", "message", "error", "start_date", "end_date", "current_date", "weekday_zh"):
        if raw.get(key) not in (None, "", [], {}):
            output[key] = raw.get(key)
    events = raw.get("events")
    if isinstance(events, list):
        output["events"] = [
            {
                field: event.get(field)
                for field in ("event_id", "date", "weekday_zh", "time", "title", "location", "type", "department")
                if isinstance(event, dict) and event.get(field) not in (None, "", [], {})
            }
            for event in events[:10]
            if isinstance(event, dict)
        ]
    event = raw.get("event")
    if isinstance(event, dict):
        output["event"] = {
                field: event.get(field)
                for field in ("event_id", "date", "weekday_zh", "time", "title", "location", "type", "department")
                if event.get(field) not in (None, "", [], {})
        }
    records = raw.get("records")
    if isinstance(records, list):
        output["records"] = records[:10]
    return output or {key: raw.get(key) for key in list(raw)[:8]}


def _action_signature(action: dict[str, Any], task: dict[str, Any]) -> str:
    kind = str(action.get("next_action") or "").strip()
    batch_tasks = action.get("_batch_tasks") if isinstance(action.get("_batch_tasks"), list) else []
    if kind == "search_rag" and batch_tasks:
        ids = [str(item.get("task_id") or "") for item in batch_tasks if isinstance(item, dict)]
        return "search_rag_batch:" + ",".join(ids)
    if kind == "call_tool":
        tool = str(action.get("tool_name") or task.get("tool") or task.get("tool_name") or "").strip()
        tool_input = action.get("tool_input") if isinstance(action.get("tool_input"), dict) else task.get("tool_input")
        return f"call_tool:{tool}:{json.dumps(tool_input or {}, ensure_ascii=False, sort_keys=True, default=str)}"
    if kind == "search_rag":
        query = str(action.get("rag_query") or task.get("rag_query") or task.get("query") or task.get("objective") or "").strip()
        return f"search_rag:{query}"
    return kind


def _is_duplicate_read_action(action: dict[str, Any], task: dict[str, Any]) -> bool:
    if str(action.get("next_action") or "") != "call_tool":
        return False
    tool = str(action.get("tool_name") or task.get("tool") or task.get("tool_name") or "").strip()
    tool_input = action.get("tool_input") if isinstance(action.get("tool_input"), dict) else task.get("tool_input")
    action_name = str((tool_input or {}).get("action") or task.get("action") or "").strip().lower()
    return tool == "manage_company_calendar" and action_name == "query"


def _merge_execution_status(current: str, observed: str) -> str:
    normalized = str(observed or "").lower()
    if normalized in {"blocked", "need_clarification", "failed", "error"}:
        return normalized
    if normalized in {"empty", "no_evidence", "insufficient_evidence"} and current == "success":
        return "partial"
    return current


class ReActExecutor:
    """Single bounded executor for tool, RAG, mixed, and query-first plans.

    The LLM may propose the next structured action, but this executor owns
    hard limits, duplicate prevention, task scope, and the final execution call.
    """

    def __init__(self, max_steps: int = 5) -> None:
        self.max_steps = min(max(1, int(max_steps or 5)), 5)

    @staticmethod
    def _tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
        queue = state.get("task_queue") if isinstance(state.get("task_queue"), list) else []
        if queue:
            return [dict(task) for task in queue if isinstance(task, dict)]
        plan = state.get("execution_plan") if isinstance(state.get("execution_plan"), dict) else {}
        return [dict(task) for task in (plan.get("tasks") or []) if isinstance(task, dict)]

    @staticmethod
    def _remaining_tasks(state: dict[str, Any], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        completed = {str(item) for item in (state.get("completed_tasks") or [])}
        return [task for task in tasks if _task_id(task) not in completed]

    @staticmethod
    def _fallback_action(remaining: list[dict[str, Any]]) -> dict[str, Any]:
        if not remaining:
            return {"next_action": "finish", "finish_reason": "all tasks completed"}
        task = remaining[0]
        kind = str(task.get("kind") or "").lower()
        if kind == "tool":
            return {
                "next_action": "call_tool",
                "task_id": _task_id(task),
                "tool_name": task.get("tool") or task.get("tool_name"),
                "tool_input": task.get("tool_input") or {},
            }
        if kind == "rag":
            return {
                "next_action": "search_rag",
                "task_id": _task_id(task),
                "rag_query": task.get("rag_query") or task.get("query") or task.get("objective") or "",
            }
        return {"next_action": "finish", "task_id": _task_id(task), "finish_reason": "answer task uses resolved facts"}


    @staticmethod
    def _validated_executable_ids(state: dict[str, Any]) -> set[str]:
        validation = state.get("plan_validation") if isinstance(state.get("plan_validation"), dict) else {}
        if str(validation.get("validation_status") or "").lower() not in {"valid", "partial"}:
            return set()
        executable = validation.get("executable_tasks") if isinstance(validation.get("executable_tasks"), list) else []
        return {_task_id(task) for task in executable if isinstance(task, dict) and _task_id(task)}

    @staticmethod
    def _can_direct_execute(state: dict[str, Any], task: dict[str, Any], completed_ids: set[str]) -> bool:
        task_id = _task_id(task)
        if not task_id or task_id not in ReActExecutor._validated_executable_ids(state):
            return False
        dependencies = [str(dep).strip() for dep in (task.get("depends_on") or []) if str(dep).strip()]
        if any(dep not in completed_ids for dep in dependencies):
            return False
        kind = str(task.get("kind") or "").lower()
        if kind == "tool":
            tool = str(task.get("tool") or task.get("tool_name") or "").strip()
            action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").strip()
            return bool(tool and action and isinstance(task.get("tool_input") or {}, dict)) and task_id not in completed_ids
        if kind == "rag":
            if dependencies:
                return False
            query = str(task.get("rag_query") or task.get("query") or task.get("objective") or "").strip()
            return bool(query) and task_id not in completed_ids
        return False

    @staticmethod
    def _direct_action_from_validated_plan(state: dict[str, Any], remaining: list[dict[str, Any]], completed_ids: set[str]) -> dict[str, Any] | None:
        if not remaining:
            return None
        batch = ReActExecutor._direct_rag_batch_from_validated_plan(state, remaining, completed_ids)
        if batch is not None:
            return batch
        task = remaining[0]
        if not ReActExecutor._can_direct_execute(state, task, completed_ids):
            return None
        return ReActExecutor._fallback_action([task])

    @staticmethod
    def _direct_rag_batch_from_validated_plan(state: dict[str, Any], remaining: list[dict[str, Any]], completed_ids: set[str]) -> dict[str, Any] | None:
        if not remaining or str(remaining[0].get("kind") or "").lower() != "rag":
            return None
        batch: list[dict[str, Any]] = []
        for task in remaining:
            if str(task.get("kind") or "").lower() != "rag":
                continue
            if not ReActExecutor._can_direct_execute(state, task, completed_ids):
                continue
            batch.append(task)
        if len(batch) <= 1:
            return None
        first = batch[0]
        return {
            "next_action": "search_rag",
            "task_id": _task_id(first),
            "rag_query": first.get("rag_query") or first.get("query") or first.get("objective") or "",
            "_batch_tasks": [dict(item) for item in batch],
        }

    def _coerce_action(self, action: Any, remaining: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(action, dict):
            return self._fallback_action(remaining)
        name = str(action.get("next_action") or action.get("action") or "").strip()
        if name not in {"call_tool", "search_rag", "finish", "ask_clarification"}:
            return self._fallback_action(remaining)
        output = dict(action)
        output["next_action"] = name
        if name in {"call_tool", "search_rag"} and not output.get("task_id") and remaining:
            output["task_id"] = _task_id(remaining[0])
        return output

    @staticmethod
    def _task_by_action(tasks: list[dict[str, Any]], action: dict[str, Any]) -> dict[str, Any]:
        wanted = str(action.get("task_id") or "").strip()
        for task in tasks:
            if _task_id(task) == wanted:
                return task
        if tasks:
            return tasks[0]
        return {}

    @staticmethod
    def _validate_action_scope(
        action: dict[str, Any],
        remaining: list[dict[str, Any]],
        all_tasks: list[dict[str, Any]],
        completed_ids: set[str],
    ) -> None:
        name = str(action.get("next_action") or "")
        if name == "ask_clarification":
            return
        if name == "finish":
            executable_remaining = [
                task for task in remaining if str(task.get("kind") or "").lower() in {"tool", "rag"}
            ]
            if executable_remaining:
                raise ReActGuardrailViolation("finish blocked: remaining executable tasks exist")
            return
        task_id = str(action.get("task_id") or "").strip()
        task_ids = {_task_id(task) for task in all_tasks}
        if task_id and task_id not in task_ids:
            raise ReActGuardrailViolation(f"action task_id outside approved plan: {task_id}")
        task = ReActExecutor._task_by_action(all_tasks, action)
        dependencies = [str(dep).strip() for dep in (task.get("depends_on") or []) if str(dep).strip()]
        missing_dependencies = [dep for dep in dependencies if dep not in completed_ids]
        if missing_dependencies:
            raise ReActGuardrailViolation(f"depends_on not completed for task {task_id}: {', '.join(missing_dependencies)}")
        remaining_ids = {_task_id(candidate) for candidate in remaining}
        if task_id and task_id not in remaining_ids:
            raise ReActGuardrailViolation(f"action repeats completed task: {task_id}")
        batch_tasks = action.get("_batch_tasks") if isinstance(action.get("_batch_tasks"), list) else []
        if batch_tasks:
            if name != "search_rag":
                raise ReActGuardrailViolation("batch execution only supports search_rag")
            for batch_task in batch_tasks:
                if not isinstance(batch_task, dict):
                    raise ReActGuardrailViolation("invalid batch task")
                batch_task_id = _task_id(batch_task)
                if batch_task_id not in remaining_ids:
                    raise ReActGuardrailViolation(f"batch task outside remaining plan: {batch_task_id}")
                if str(batch_task.get("kind") or "").lower() != "rag":
                    raise ReActGuardrailViolation("batch execution only supports rag tasks")
                deps = [str(dep).strip() for dep in (batch_task.get("depends_on") or []) if str(dep).strip()]
                if deps:
                    raise ReActGuardrailViolation(f"batch task has dependencies: {batch_task_id}")
        if name == "call_tool" and str(task.get("kind") or "") != "tool":
            raise ReActGuardrailViolation("call_tool action is not approved for this task")
        if name == "search_rag" and str(task.get("kind") or "") != "rag":
            raise ReActGuardrailViolation("search_rag action is not approved for this task")
        proposed_tool = str(action.get("tool_name") or "").strip()
        approved_tool = str(task.get("tool") or task.get("tool_name") or "").strip()
        if name == "call_tool" and proposed_tool and approved_tool and proposed_tool != approved_tool:
            raise ReActGuardrailViolation(f"tool outside approved task: {proposed_tool}")

    def run(
        self,
        state: dict[str, Any],
        *,
        next_action: NextAction,
        call_tool: CallTool,
        search_rag: SearchRAG,
    ) -> ReActExecutionResult:
        steps: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        overall_status = "success"
        observations = state.setdefault("observations", [])

        for step_number in range(1, self.max_steps + 1):
            tasks = self._tasks(state)
            remaining = self._remaining_tasks(state, tasks)
            if not remaining:
                finish = {
                    "step": step_number,
                    "action": "finish",
                    "status": "success",
                    "summary": "all tasks completed",
                    "facts": [],
                }
                steps.append(finish)
                observations.append({"type": "react_observation", **finish})
                return ReActExecutionResult(status=overall_status, steps=tuple(steps), finish_reason="all tasks completed")

            completed_ids = {str(item) for item in (state.get("completed_tasks") or [])}
            completed_ids.update({_task_id(task) for task in tasks if _task_id(task) not in {_task_id(item) for item in remaining}})
            direct_action = self._direct_action_from_validated_plan(state, remaining, completed_ids)
            if direct_action is not None:
                action = self._coerce_action(direct_action, remaining)
                next_action_ms = 0.0
                next_action_source = "deterministic"
            else:
                next_action_started = time.perf_counter()
                action = self._coerce_action(next_action(state, step_number, remaining), remaining)
                next_action_ms = round((time.perf_counter() - next_action_started) * 1000, 2)
                next_action_source = "llm"
            action["_next_action_ms"] = next_action_ms
            action["_next_action_source"] = next_action_source
            self._validate_action_scope(action, remaining, tasks, completed_ids)
            task = self._task_by_action(tasks, action)
            name = str(action.get("next_action") or "")

            if name == "finish":
                step = {
                    "step": step_number,
                    "task_id": action.get("task_id"),
                    "action": "finish",
                    "status": "success",
                    "summary": str(action.get("finish_reason") or "finish"),
                    "facts": [],
                }
                steps.append(step)
                observations.append({"type": "react_observation", **step})
                return ReActExecutionResult(status="success", steps=tuple(steps), finish_reason=step["summary"])

            if name == "ask_clarification":
                step = {
                    "step": step_number,
                    "task_id": action.get("task_id"),
                    "action": "ask_clarification",
                    "status": "need_clarification",
                    "summary": str(action.get("finish_reason") or action.get("clarification") or "需要补充信息。"),
                    "facts": [],
                }
                steps.append(step)
                observations.append({"type": "react_observation", **step})
                state["final_answer"] = step["summary"]
                state["intent"] = "need_clarification"
                state["route"] = "direct"
                return ReActExecutionResult(status="need_clarification", steps=tuple(steps), finish_reason=step["summary"])

            signature = _action_signature(action, task)
            if signature in seen_signatures:
                if _is_duplicate_read_action(action, task):
                    task_id = _task_id(task)
                    if task_id and task_id not in set(state.get("completed_tasks") or []):
                        state.setdefault("completed_tasks", []).append(task_id)
                    step = {
                        "step": step_number,
                        "task_id": task_id,
                        "action": name,
                        "status": "success",
                        "summary": "duplicate query reused previous observation",
                        "raw_result": {"status": "reused"},
                        "facts": [],
                        "next_action_source": next_action_source,
                        "next_action_ms": next_action_ms,
                    }
                    steps.append(step)
                    observations.append({"type": "react_observation", **step})
                    continue
                raise ReActGuardrailViolation(f"duplicate action blocked: {signature}")
            seen_signatures.add(signature)

            raw_observation = call_tool(task, action) if name == "call_tool" else search_rag(task, action)
            batch_results = raw_observation.get("batch_results") if isinstance(raw_observation.get("batch_results"), list) else []
            if batch_results:
                terminal_status = "success"
                terminal_summary = "all batched rag tasks completed"
                for item in batch_results:
                    if not isinstance(item, dict):
                        continue
                    item_status = str(item.get("status") or "success")
                    item_task_id = str(item.get("task_id") or "").strip()
                    if item_status in {"success", "ok", "empty", "no_evidence"} and item_task_id and item_task_id not in set(state.get("completed_tasks") or []):
                        state.setdefault("completed_tasks", []).append(item_task_id)
                    overall_status = _merge_execution_status(overall_status, item_status)
                    step = {
                        "step": len(steps) + 1,
                        "task_id": item_task_id,
                        "action": name,
                        "status": item_status,
                        "summary": str(item.get("summary") or ""),
                        "raw_result": _compact_raw_result(item.get("raw_result") or {}),
                        "facts": item.get("facts") or [],
                        "next_action_source": next_action_source,
                        "next_action_ms": next_action_ms,
                    }
                    steps.append(step)
                    observations.append({"type": "react_observation", **step})
                    merged_terminal = _merge_execution_status(terminal_status, item_status)
                    if merged_terminal != terminal_status:
                        terminal_status = merged_terminal
                        terminal_summary = step["summary"]
                if terminal_status != "success":
                    if terminal_status != "partial":
                        return ReActExecutionResult(status=terminal_status, steps=tuple(steps), finish_reason=terminal_summary)
            else:
                status = str(raw_observation.get("status") or "success")
                task_id = _task_id(task)
                if status in {"success", "ok", "empty", "no_evidence"} and task_id and task_id not in set(state.get("completed_tasks") or []):
                    state.setdefault("completed_tasks", []).append(task_id)
                overall_status = _merge_execution_status(overall_status, status)
                step = {
                    "step": step_number,
                    "task_id": task_id,
                    "action": name,
                    "status": status,
                    "summary": str(raw_observation.get("summary") or ""),
                    "raw_result": _compact_raw_result(raw_observation.get("raw_result") or {}),
                    "facts": raw_observation.get("facts") or [],
                    "next_action_source": next_action_source,
                    "next_action_ms": next_action_ms,
                }
                steps.append(step)
                observations.append({"type": "react_observation", **step})
                if status in {"blocked", "need_clarification", "failed", "error"}:
                    return ReActExecutionResult(status=status, steps=tuple(steps), finish_reason=step["summary"])
            next_remaining = self._remaining_tasks(state, self._tasks(state))
            executable_remaining = [
                item for item in next_remaining if str(item.get("kind") or "").lower() in {"tool", "rag"}
            ]
            if not next_remaining or not executable_remaining:
                return ReActExecutionResult(status=overall_status, steps=tuple(steps), finish_reason="all tasks completed")

        return ReActExecutionResult(status="partial", steps=tuple(steps), finish_reason="max steps reached")


__all__ = ["ReActExecutor", "ReActExecutionResult", "ReActGuardrailViolation"]
