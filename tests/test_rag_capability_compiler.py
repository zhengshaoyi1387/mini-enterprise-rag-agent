from __future__ import annotations

from mini_rag.capabilities.rag.compiler import collect_ready_rag_tasks, compile_search_tasks, normalize_query_key


def test_collect_ready_rag_tasks_respects_dependencies_and_executed_queries() -> None:
    state = {
        "execution_plan": {
            "tasks": [
                {"task_id": "done", "kind": "rag", "query": "已查过"},
                {"task_id": "blocked", "kind": "rag", "query": "等待工具", "depends_on": ["tool1"]},
                {"task_id": "ready", "kind": "rag", "query": "报销制度"},
            ]
        },
        "completed_tasks": ["done"],
        "_executed_query_keys": [normalize_query_key("已查过")],
    }

    tasks = collect_ready_rag_tasks(state, max_tasks=3)

    assert [task["task_id"] for task in tasks] == ["ready"]


def test_compile_search_tasks_uses_multi_entity_fallback_without_expanding_scope() -> None:
    state = {
        "standalone_query": "比较报销制度和差旅制度",
        "intent": "rag_compare",
        "entities": ["报销制度", "差旅制度"],
    }

    tasks = compile_search_tasks(state, top_k=4, candidate_k=12, max_tasks=3)

    assert [task["query"] for task in tasks] == ["报销制度", "差旅制度"]
    assert all(task["purpose"] == "answer_question" for task in tasks)
    assert all("_plan_task" in task for task in tasks)


def test_compile_search_tasks_dedupes_task_queries_and_keeps_task_metadata() -> None:
    state = {
        "execution_plan": {
            "tasks": [
                {"task_id": "a", "kind": "rag", "objective": "A", "query": " 公司报销制度 "},
                {"task_id": "b", "kind": "rag", "objective": "B", "query": "公司报销制度"},
            ]
        }
    }

    tasks = compile_search_tasks(state, top_k=5, candidate_k=20, max_tasks=5)

    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "a"
    assert tasks[0]["objective"] == "A"
    assert tasks[0]["top_k"] == 5
    assert tasks[0]["candidate_k"] == 20
