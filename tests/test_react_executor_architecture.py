from __future__ import annotations

from mini_rag.config import Settings
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state
from mini_rag.orchestration.react_executor import ReActExecutor, ReActGuardrailViolation


class NoopLLM:
    def invoke(self, _messages):
        class Message:
            content = '{"next_action":"finish","finish_reason":"done"}'

        return Message()


def make_settings(tmp_path):
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_workflow_routes_simple_datetime_through_react_executor(tmp_path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("明天是几号？", role="employee", override_now="2026-05-18T09:30:00+08:00")
    state["raw_plan"] = {
        "overall_intent": "datetime",
        "tasks": [{"task_id": "t1", "kind": "answer", "objective": "回答明天是几号", "time_expression": "明天"}],
    }
    state["execution_plan"] = {"tasks": list(state["raw_plan"]["tasks"])}

    state = nodes.build_runtime_context(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    state = nodes.react_execute(state)

    assert state["react_status"] == "success"
    assert state["resolved_time_facts"][0]["items"][0]["start_date"] == "2026-05-19"


def test_react_executor_blocks_action_outside_approved_plan() -> None:
    executor = ReActExecutor(max_steps=3)
    state = {
        "question": "查询明天会议",
        "execution_plan": {
            "tasks": [
                {"task_id": "t1", "kind": "tool", "tool": "manage_company_calendar", "action": "query", "tool_input": {}}
            ]
        },
        "completed_tasks": [],
        "observations": [],
    }

    try:
        executor.run(
            state,
            next_action=lambda *_args: {"next_action": "call_tool", "task_id": "unknown", "tool_name": "manage_company_calendar"},
            call_tool=lambda *_args: {"status": "success"},
            search_rag=lambda *_args: {"status": "success"},
        )
    except ReActGuardrailViolation as exc:
        assert "outside approved plan" in str(exc)
    else:
        raise AssertionError("out-of-plan ReAct action should be blocked")


def test_react_executor_blocks_finish_when_tool_tasks_remain() -> None:
    executor = ReActExecutor(max_steps=3)
    state = {
        "question": "查询明天会议",
        "execution_plan": {
            "tasks": [
                {"task_id": "t1", "kind": "tool", "tool": "manage_company_calendar", "action": "query", "tool_input": {}}
            ]
        },
        "completed_tasks": [],
        "observations": [],
    }

    try:
        executor.run(
            state,
            next_action=lambda *_args: {"next_action": "finish", "finish_reason": "done"},
            call_tool=lambda *_args: {"status": "success"},
            search_rag=lambda *_args: {"status": "success"},
        )
    except ReActGuardrailViolation as exc:
        assert "remaining executable tasks" in str(exc)
    else:
        raise AssertionError("finish should be blocked while tool tasks remain")


def test_react_executor_enforces_depends_on_before_task_execution() -> None:
    executor = ReActExecutor(max_steps=3)
    state = {
        "question": "先查再改",
        "execution_plan": {
            "tasks": [
                {"task_id": "query", "kind": "tool", "tool": "manage_company_calendar", "action": "query", "tool_input": {}},
                {
                    "task_id": "update",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "depends_on": ["query"],
                    "tool_input": {"action": "update", "event_id": "EVT-20260518-0001", "location": "会议室B"},
                },
            ]
        },
        "completed_tasks": [],
        "observations": [],
    }

    try:
        executor.run(
            state,
            next_action=lambda *_args: {"next_action": "call_tool", "task_id": "update", "tool_name": "manage_company_calendar"},
            call_tool=lambda *_args: {"status": "success"},
            search_rag=lambda *_args: {"status": "success"},
        )
    except ReActGuardrailViolation as exc:
        assert "depends_on" in str(exc)
    else:
        raise AssertionError("dependent task should be blocked before dependency completion")


def test_react_executor_returns_success_when_fifth_task_completes() -> None:
    executor = ReActExecutor(max_steps=5)
    state = {
        "question": "执行五个工具任务",
        "execution_plan": {
            "tasks": [
                {"task_id": f"t{idx}", "kind": "tool", "tool": "manage_company_calendar", "action": "query", "tool_input": {"idx": idx}}
                for idx in range(1, 6)
            ]
        },
        "completed_tasks": [],
        "observations": [],
    }

    result = executor.run(
        state,
        next_action=lambda _state, _step, remaining: {
            "next_action": "call_tool",
            "task_id": remaining[0]["task_id"],
            "tool_name": "manage_company_calendar",
            "tool_input": remaining[0]["tool_input"],
        },
        call_tool=lambda *_args: {"status": "success", "summary": "ok", "raw_result": {}},
        search_rag=lambda *_args: {"status": "success", "summary": "ok", "raw_result": {}},
    )

    assert result.status == "success"
    assert len(result.steps) == 5
    assert result.finish_reason == "all tasks completed"


def test_react_executor_skips_next_action_for_valid_simple_tool_task() -> None:
    executor = ReActExecutor(max_steps=3)
    state = {
        "question": "查询明天会议",
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "start_date": "2026-05-20", "end_date": "2026-05-20"},
                }
            ]
        },
        "plan_validation": {
            "validation_status": "valid",
            "executable_tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "start_date": "2026-05-20", "end_date": "2026-05-20"},
                }
            ],
        },
        "completed_tasks": [],
        "observations": [],
    }

    def fail_next_action(*_args):
        raise AssertionError("simple executable task should not call react_execute.next_action LLM")

    result = executor.run(
        state,
        next_action=fail_next_action,
        call_tool=lambda task, action: {
            "status": "success",
            "summary": f"called {action['next_action']} for {task['task_id']}",
            "raw_result": {"events": []},
        },
        search_rag=lambda *_args: {"status": "success"},
    )

    assert result.status == "success"
    assert result.steps[0]["action"] == "call_tool"
    assert result.steps[0]["next_action_source"] == "deterministic"
    assert result.steps[0]["next_action_ms"] == 0


def test_react_executor_batches_independent_validated_rag_tasks() -> None:
    executor = ReActExecutor(max_steps=5)
    tasks = [
        {"task_id": "t1", "kind": "rag", "query": "制度 A", "rag_query": "制度 A", "tool_input": {}},
        {"task_id": "t2", "kind": "rag", "query": "制度 B", "rag_query": "制度 B", "tool_input": {}},
        {"task_id": "t3", "kind": "rag", "query": "制度 C", "rag_query": "制度 C", "tool_input": {}},
    ]
    state = {
        "question": "三个独立制度问题",
        "execution_plan": {"tasks": tasks},
        "plan_validation": {"validation_status": "valid", "executable_tasks": tasks},
        "completed_tasks": [],
        "observations": [],
    }

    def fail_next_action(*_args):
        raise AssertionError("independent validated rag tasks should not call next_action LLM")

    seen_batches: list[list[str]] = []

    def search_rag(task, action):
        batch = action.get("_batch_tasks") or []
        seen_batches.append([item["task_id"] for item in batch])
        return {
            "status": "success",
            "batch_results": [
                {
                    "task_id": item["task_id"],
                    "status": "success",
                    "summary": f"ok {item['task_id']}",
                    "raw_result": {"sources": []},
                    "facts": [],
                }
                for item in batch
            ],
        }

    result = executor.run(
        state,
        next_action=fail_next_action,
        call_tool=lambda *_args: {"status": "success"},
        search_rag=search_rag,
    )

    assert result.status == "success"
    assert seen_batches == [["t1", "t2", "t3"]]
    assert [step["task_id"] for step in result.steps] == ["t1", "t2", "t3"]
    assert all(step["next_action_source"] == "deterministic" for step in result.steps)
    assert state["completed_tasks"] == ["t1", "t2", "t3"]


def test_react_executor_returns_partial_when_validated_rag_task_has_no_evidence() -> None:
    executor = ReActExecutor(max_steps=3)
    tasks = [
        {
            "task_id": "t1",
            "kind": "rag",
            "query": "出差酒店费用是否可以报销",
            "rag_query": "出差酒店费用是否可以报销",
            "tool_input": {},
        }
    ]
    state = {
        "question": "出差酒店费用是否可以报销？",
        "execution_plan": {"tasks": tasks},
        "plan_validation": {"validation_status": "valid", "executable_tasks": tasks},
        "completed_tasks": [],
        "observations": [],
    }

    def fail_next_action(*_args):
        raise AssertionError("validated simple rag task should execute deterministically")

    result = executor.run(
        state,
        next_action=fail_next_action,
        call_tool=lambda *_args: {"status": "success"},
        search_rag=lambda *_args: {
            "status": "empty",
            "summary": "no supporting evidence",
            "raw_result": {"sources": [], "related_sources": [{"source_id": "finance-1"}]},
        },
    )

    assert result.status == "partial"
    assert result.steps[0]["status"] == "empty"
    assert state["completed_tasks"] == ["t1"]


def test_react_executor_does_not_batch_dependent_rag_tasks() -> None:
    executor = ReActExecutor(max_steps=5)
    tasks = [
        {"task_id": "t1", "kind": "rag", "query": "先查 A", "rag_query": "先查 A", "tool_input": {}},
        {"task_id": "t2", "kind": "rag", "query": "再查 B", "rag_query": "再查 B", "depends_on": ["t1"], "tool_input": {}},
    ]
    state = {
        "question": "有依赖的 RAG",
        "execution_plan": {"tasks": tasks},
        "plan_validation": {"validation_status": "valid", "executable_tasks": tasks},
        "completed_tasks": [],
        "observations": [],
    }
    actions_seen: list[str] = []

    next_action_calls = {"count": 0}

    def next_action(_state, _step, remaining):
        next_action_calls["count"] += 1
        return {"next_action": "search_rag", "task_id": remaining[0]["task_id"], "rag_query": remaining[0]["query"]}

    result = executor.run(
        state,
        next_action=next_action,
        call_tool=lambda *_args: {"status": "success"},
        search_rag=lambda task, action: actions_seen.append(task["task_id"]) or {"status": "success", "summary": "ok", "raw_result": {}},
    )

    assert result.status == "success"
    assert actions_seen == ["t1", "t2"]
    assert len(result.steps) == 2
    assert next_action_calls["count"] == 1
    assert result.steps[0]["next_action_source"] == "deterministic"
    assert result.steps[1]["next_action_source"] == "llm"


def test_batched_rag_callback_keeps_each_task_query_isolated(tmp_path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("多个独立 RAG 问题", role="admin", override_now="2026-05-20T09:30:00+08:00")
    state["used_kbs"] = ["finance", "hr", "it", "product", "public"]
    state["task_results"] = []
    tasks = [
        {
            "task_id": "t1",
            "kind": "rag",
            "objective": "查询考勤制度文档编号",
            "query": "考勤与休假管理制度的文档编号",
            "rag_query": "考勤与休假管理制度的文档编号",
            "tool_input": {},
        },
        {
            "task_id": "t2",
            "kind": "rag",
            "objective": "查询8000元以上报销注意事项",
            "query": "8000元以上报销 注意事项",
            "rag_query": "8000元以上报销 注意事项",
            "tool_input": {},
        },
        {
            "task_id": "t3",
            "kind": "rag",
            "objective": "查询VPN远程访问安全要求",
            "query": "VPN远程访问 安全要求",
            "rag_query": "VPN远程访问 安全要求",
            "tool_input": {},
        },
    ]

    captured_pending: list[list[dict]] = []

    class FakeRAGService:
        def retrieve(self, current_state):
            pending = [dict(item) for item in current_state.get("pending_search_tasks") or []]
            captured_pending.append(pending)
            for item in pending:
                query = item["query"]
                task_id = item["task_id"]
                current_state.setdefault("task_results", []).append(
                    {
                        "task_id": task_id,
                        "kind": "rag",
                        "objective": item.get("objective") or query,
                        "status": "ok",
                        "query": query,
                        "executed_queries": [query],
                        "sources": [{"chunk_id": f"{task_id}-source", "preview": query}],
                        "candidate_sources": [{"chunk_id": f"{task_id}-candidate", "preview": query}],
                        "evidence_summary": f"evidence for {task_id}: {query}",
                    }
                )
            return current_state

    nodes.rag_service = FakeRAGService()  # type: ignore[assignment]
    callback = nodes._make_rag_callback(state)
    result = callback(
        tasks[0],
        {
            "next_action": "search_rag",
            "task_id": "t1",
            # The batch action naturally carries the first query. This must not override t2/t3.
            "rag_query": "考勤与休假管理制度的文档编号",
            "_batch_tasks": [dict(item) for item in tasks],
            "_next_action_source": "deterministic",
            "_next_action_ms": 0.0,
        },
    )

    assert result["status"] == "success"
    assert [[item["task_id"], item["query"]] for item in captured_pending[0]] == [
        ["t1", "考勤与休假管理制度的文档编号"],
        ["t2", "8000元以上报销 注意事项"],
        ["t3", "VPN远程访问 安全要求"],
    ]
    assert [item["query"] for item in state["task_results"]] == [
        "考勤与休假管理制度的文档编号",
        "8000元以上报销 注意事项",
        "VPN远程访问 安全要求",
    ]
    assert [item["task_id"] for item in result["batch_results"]] == ["t1", "t2", "t3"]
