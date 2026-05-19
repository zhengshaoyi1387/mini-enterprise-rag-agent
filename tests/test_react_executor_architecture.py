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
