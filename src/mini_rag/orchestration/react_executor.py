from __future__ import annotations

import json
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
    if kind == "call_tool":
        tool = str(action.get("tool_name") or task.get("tool") or task.get("tool_name") or "").strip()
        tool_input = action.get("tool_input") if isinstance(action.get("tool_input"), dict) else task.get("tool_input")
        return f"call_tool:{tool}:{json.dumps(tool_input or {}, ensure_ascii=False, sort_keys=True, default=str)}"
    if kind == "search_rag":
        query = str(action.get("rag_query") or task.get("rag_query") or task.get("query") or task.get("objective") or "").strip()
        return f"search_rag:{query}"
    return kind


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
                return ReActExecutionResult(status="success", steps=tuple(steps), finish_reason="all tasks completed")

            action = self._coerce_action(next_action(state, step_number, remaining), remaining)
            completed_ids = {str(item) for item in (state.get("completed_tasks") or [])}
            completed_ids.update({_task_id(task) for task in tasks if _task_id(task) not in {_task_id(item) for item in remaining}})
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
                raise ReActGuardrailViolation(f"duplicate action blocked: {signature}")
            seen_signatures.add(signature)

            raw_observation = call_tool(task, action) if name == "call_tool" else search_rag(task, action)
            status = str(raw_observation.get("status") or "success")
            task_id = _task_id(task)
            if status in {"success", "ok", "empty", "no_evidence"} and task_id and task_id not in set(state.get("completed_tasks") or []):
                state.setdefault("completed_tasks", []).append(task_id)
            step = {
                "step": step_number,
                "task_id": task_id,
                "action": name,
                "status": status,
                "summary": str(raw_observation.get("summary") or ""),
                "raw_result": _compact_raw_result(raw_observation.get("raw_result") or {}),
                "facts": raw_observation.get("facts") or [],
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
                return ReActExecutionResult(status="success", steps=tuple(steps), finish_reason="all tasks completed")

        return ReActExecutionResult(status="partial", steps=tuple(steps), finish_reason="max steps reached")


__all__ = ["ReActExecutor", "ReActExecutionResult", "ReActGuardrailViolation"]
