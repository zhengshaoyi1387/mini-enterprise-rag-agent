from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.orchestration.state_views import (
    get_answer_state,
    get_execution_state,
    get_plan_state,
    get_runtime_context,
    sync_legacy_state_fields,
)


class Message:
    def __init__(self, content: str):
        self.content = content


class QueueLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.contents:
            return Message(self.contents.pop(0))
        return Message('{"next_action":"finish","finish_reason":"done"}')


class EmptyRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query: str, **_kwargs):
        self.queries.append(query)
        return [], {"retrieval_cache_hit": False}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_runtime_context_view_is_populated_by_build_runtime_context(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=QueueLLM([]), retriever=EmptyRetriever())
    state = create_initial_state("你好", role="employee", user_id="u1", override_now="2026-05-18T09:30:00+08:00")

    state = nodes.build_runtime_context(state)

    runtime = get_runtime_context(state)
    assert runtime["user_id"] == "u1"
    assert runtime["role"] == "employee"
    assert runtime["time_context_result"]["current_date"] == "2026-05-18"
    assert "permissions" in runtime
    assert "capability_catalog" in runtime


def test_plan_execution_and_answer_state_views_follow_mainline_nodes(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"smalltalk","requires_tools":false,"requires_rag":false,"tasks":[],"answer_style":"concise"}',
            "你好，我在。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=EmptyRetriever())
    state = create_initial_state("你好", role="employee", override_now="2026-05-18T09:30:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    plan_state = get_plan_state(state)
    assert plan_state["overall_intent"] == "smalltalk"
    assert plan_state["execution_plan"]["tasks"] == []

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    assert get_plan_state(state)["plan_validation"]["validation_status"] == "valid"

    state = nodes.react_execute(state)
    execution_state = get_execution_state(state)
    assert execution_state["react_status"] == "success"
    assert execution_state["react_steps"]
    assert execution_state["task_results"] == []

    state = nodes.answer_with_llm(state)
    answer_state = get_answer_state(state)
    assert answer_state["answer_packet"]["status"] == "success"
    assert answer_state["completion_assessment"]["ready_to_answer"] is True
    assert answer_state["final_answer"] == "你好，我在。"


def test_sync_legacy_state_fields_prefers_standard_views_and_repairs_completion_conflict() -> None:
    state = {
        "route": "rag",
        "intent": "smalltalk",
        "execution_plan": {"tasks": [{"task_id": "t1", "kind": "rag"}]},
        "completed_tasks": [],
        "completion_assessment": {"ready_to_answer": True, "execution_status": "need_clarification"},
        "plan_state": {
            "overall_intent": "smalltalk",
            "route": "direct",
            "intent": "smalltalk",
            "execution_plan": {"tasks": []},
        },
        "execution_state": {"react_status": "need_clarification", "completed_tasks": []},
        "answer_state": {"completion_assessment": {"ready_to_answer": True, "execution_status": "need_clarification"}},
    }

    sync_legacy_state_fields(state)

    assert state["route"] == "direct"
    assert state["intent"] == "smalltalk"
    assert state["execution_plan"]["tasks"] == []
    assert state["completion_assessment"]["ready_to_answer"] is False
    assert state["answer_state"]["completion_assessment"]["ready_to_answer"] is False


def test_mixed_plan_state_intent_survives_tool_execution_route_changes(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"mixed","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"att","kind":"tool","objective":"查上周考勤","tool_name":"query_attendance_summary",'
            '"action":"query","time_expression":"上周","tool_input":{"department":"all","include_records":false}}],'
            '"answer_style":"concise"}',
            '{"next_action":"call_tool","task_id":"att","tool_name":"query_attendance_summary"}',
            "考勤已查询。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=EmptyRetriever())
    state = create_initial_state("查上周考勤并总结", role="admin", override_now="2026-05-18T09:30:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    state = nodes.react_execute(state)

    assert get_plan_state(state)["overall_intent"] == "mixed"
    assert state["plan_state"]["overall_intent"] == "mixed"
    assert state["execution_state"]["react_status"] == "success"
