from __future__ import annotations

from typing import Any


def normalize_query_key(query: str) -> str:
    return " ".join(str(query or "").strip().split()).lower()


def _task_query(task: dict[str, Any]) -> str:
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    return str(task.get("query") or tool_input.get("query") or "").strip()


def collect_ready_rag_tasks(state: dict[str, Any], *, max_tasks: int) -> list[dict[str, Any]]:
    completed = set(str(x) for x in (state.get("completed_tasks") or []))
    executed_keys = set(str(x) for x in (state.get("_executed_query_keys") or []))
    candidates: list[dict[str, Any]] = []
    current = state.get("current_task")
    if isinstance(current, dict) and current.get("kind") == "rag":
        candidates.append(current)
    execution_plan = state.get("execution_plan") or {}
    for task in execution_plan.get("tasks") or []:
        if isinstance(task, dict) and task.get("kind") == "rag":
            candidates.append(task)
    for task in state.get("task_queue") or []:
        if isinstance(task, dict) and task.get("kind") == "rag":
            candidates.append(task)

    ready: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, task in enumerate(candidates, start=1):
        task_id = str(task.get("task_id") or f"t{idx}")
        if task_id in seen or task_id in completed:
            continue
        deps = [str(x) for x in (task.get("depends_on") or [])]
        if any(dep not in completed for dep in deps):
            continue
        query = _task_query(task)
        if query and normalize_query_key(query) in executed_keys:
            continue
        seen.add(task_id)
        ready.append(task)
    return ready[: max(1, int(max_tasks or 1))]


def _fallback_rag_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    fallback_query = str(state.get("standalone_query") or state.get("question") or "").strip()
    if not fallback_query:
        return []
    entities = [str(x).strip() for x in (state.get("entities") or []) if str(x).strip()]
    intent = str(state.get("intent") or "")
    if intent in {"rag_explain", "rag_compare"} and len(entities) > 1:
        return [
            {
                "task_id": f"entity_{idx}",
                "kind": "rag",
                "objective": entity,
                "query": entity,
                "target_entity": entity,
                "tool": "search_knowledge_base",
                "action": "*",
                "tool_input": {"query": entity},
            }
            for idx, entity in enumerate(entities, start=1)
        ]
    current_task = state.get("current_task") if isinstance(state.get("current_task"), dict) else {}
    return [
        {
            "task_id": str(current_task.get("task_id") or "t1"),
            "kind": "rag",
            "objective": str(current_task.get("objective") or fallback_query),
            "query": fallback_query,
            "tool": "search_knowledge_base",
            "action": "*",
            "tool_input": {"query": fallback_query},
        }
    ]


def compile_search_tasks(
    state: dict[str, Any],
    *,
    top_k: int,
    candidate_k: int,
    max_tasks: int,
) -> list[dict[str, Any]]:
    """Compile structured RAG plan tasks into retriever search tasks."""

    tasks = collect_ready_rag_tasks(state, max_tasks=max_tasks)
    if not tasks:
        tasks = _fallback_rag_tasks(state)

    search_tasks: list[dict[str, Any]] = []
    for idx, task in enumerate(tasks, start=1):
        query = _task_query(task)
        if not query:
            continue
        search_tasks.append(
            {
                "query": query,
                "purpose": "answer_question",
                "target_entity": task.get("target_entity"),
                "top_k": int(task.get("top_k") or top_k),
                "candidate_k": int(task.get("candidate_k") or candidate_k),
                "task_id": str(task.get("task_id") or f"t{idx}"),
                "objective": str(task.get("objective") or query),
                "_plan_task": task,
            }
        )

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for task in search_tasks:
        key = normalize_query_key(str(task.get("query") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped[: max(1, int(max_tasks or 1))]
