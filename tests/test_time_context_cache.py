from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state


class NoopLLM:
    def invoke(self, _messages):
        class Message:
            content = '{"next_action":"finish","finish_reason":"done"}'

        return Message()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        TRACE_DIR=tmp_path / "traces",
    )


def test_agent_resolves_multiple_time_expressions_from_request_time_context(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("查明天会议，再查后天培训。", role="employee", override_now="2026-05-17T01:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "meeting",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "action": "query",
                "time_expression": "明天",
                "tool_input": {"action": "query", "event_type": "meeting"},
            },
            {
                "task_id": "training",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "action": "query",
                "time_expression": "后天",
                "tool_input": {"action": "query", "event_type": "training"},
            },
        ]
    }

    state = nodes.resolve_plan_time(state)

    first, second = state["execution_plan"]["tasks"]
    assert first["tool_input"]["start_date"] == "2026-05-18"
    assert second["tool_input"]["start_date"] == "2026-05-19"
    assert state["time_context_result"]["current_date"] == "2026-05-17"
