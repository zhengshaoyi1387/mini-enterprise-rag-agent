from __future__ import annotations

import json
from pathlib import Path

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.graph.workflow import AgenticRAGWorkflow


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class RecordingLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.contents:
            return FakeMessage(self.contents.pop(0))
        return FakeMessage("{}")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_datetime_classification_uses_default_plan_without_build_plan_llm(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "message_type": "business_question",
                    "context_usage": "none",
                    "intent": "daily_tool",
                    "route": "tool",
                    "standalone_query": "现在上海时间是多少？",
                    "risk_level": "low",
                    "selected_tool": "get_current_datetime",
                    "selected_action": "*",
                    "time_requirement": {"time_reference_type": "relative", "requires_current_datetime": True},
                    "knowledge_requirement": {"requires_company_knowledge": False, "should_use_rag": False},
                    "reason": "查询当前时间",
                },
                ensure_ascii=False,
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("现在上海时间是多少？", role="employee")
    state = nodes.load_context(state)
    state = nodes.check_permission(state)
    state = nodes.build_capability_catalog(state)
    state = nodes.build_planning_context(state)
    state = nodes.classify_intent(state)
    state = nodes.build_plan(state)

    assert [call["node"] for call in state["llm_calls"]] == ["classify_intent"]
    assert state["raw_plan"]["execution_plan"]["tasks"][0]["tool"] == "get_current_datetime"


def test_partial_datetime_classification_still_uses_build_plan_for_remaining_goal(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "message_type": "business_question",
                    "context_usage": "none",
                    "intent": "daily_tool",
                    "route": "tool",
                    "standalone_query": "现在的日期时间是多少？",
                    "risk_level": "low",
                    "selected_tool": "get_current_datetime",
                    "selected_action": "*",
                    "time_requirement": {"time_reference_type": "relative", "requires_current_datetime": True},
                    "knowledge_requirement": {"requires_company_knowledge": False, "should_use_rag": False},
                    "reason": "只覆盖当前时间子目标",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "execution_plan": {
                        "tasks": [
                            {"task_id": "t1", "kind": "tool", "tool": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}},
                            {"task_id": "t2", "kind": "tool", "tool": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "event_type": "meeting"}},
                        ]
                    }
                },
                ensure_ascii=False,
            ),
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("现在的日期时间是多少？顺便查一下明天的公司会议安排。", role="employee")
    state = nodes.load_context(state)
    state = nodes.check_permission(state)
    state = nodes.build_capability_catalog(state)
    state = nodes.build_planning_context(state)
    state = nodes.classify_intent(state)
    state = nodes.build_plan(state)

    assert [call["node"] for call in state["llm_calls"]] == ["classify_intent", "build_plan"]
    assert [task["tool"] for task in state["raw_plan"]["execution_plan"]["tasks"]] == [
        "get_current_datetime",
        "manage_company_calendar",
    ]


def test_build_plan_receives_scoped_tool_contract_only(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "execution_plan": {
                        "tasks": [
                            {
                                "task_id": "t1",
                                "kind": "tool",
                                "objective": "查询下周公司日程",
                                "tool": "manage_company_calendar",
                                "action": "query",
                                "tool_input": {"action": "query", "event_type": "all", "department": "all"},
                                "time_requirement": {
                                    "time_reference_type": "relative",
                                    "canonical_relative": "next_week",
                                    "requires_current_datetime": True,
                                },
                            }
                        ]
                    },
                    "reason": "查询日程",
                },
                ensure_ascii=False,
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("下周公司有什么安排？", role="admin")
    state = nodes.load_context(state)
    state = nodes.check_permission(state)
    state = nodes.build_capability_catalog(state)
    state = nodes.build_planning_context(state)
    state["raw_intent"] = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": "下周公司有什么安排？",
        "risk_level": "low",
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "time_requirement": {
            "time_reference_type": "relative",
            "canonical_relative": "next_week",
            "requires_current_datetime": True,
        },
        "knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False},
    }

    state = nodes.build_plan(state)

    build_user = state["llm_calls"][-1]["input"]["messages"][1]["content"]
    assert '"manage_company_calendar"' in build_user
    assert '"query"' in build_user
    assert '"get_current_datetime"' in build_user
    assert '"update"' not in build_user
    assert '"delete"' not in build_user
    assert '"query_attendance_summary"' not in build_user


def test_build_plan_omits_previous_context_when_classifier_says_none(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "execution_plan": {
                        "tasks": [
                            {
                                "task_id": "t1",
                                "kind": "tool",
                                "objective": "查询下周公司日程",
                                "tool": "manage_company_calendar",
                                "action": "query",
                                "tool_input": {"action": "query", "event_type": "all", "department": "all"},
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("下周公司有什么安排？", role="employee")
    state["planning_context"] = {
        "previous_tool_context": {
            "tool_name": "manage_company_calendar",
            "tool_input": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "result_summary": "旧上下文不应进入独立问题规划",
        }
    }
    state = nodes.check_permission(state)
    state = nodes.build_capability_catalog(state)
    state["raw_intent"] = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": "下周公司有什么安排？",
        "risk_level": "low",
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "time_requirement": {
            "time_reference_type": "relative",
            "canonical_relative": "next_week",
            "requires_current_datetime": True,
        },
        "knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False},
    }

    state = nodes.build_plan(state)

    build_user = state["llm_calls"][-1]["input"]["messages"][1]["content"]
    assert "旧上下文不应进入独立问题规划" not in build_user
    assert "previous_tool_context" not in build_user


def test_workflow_skips_build_plan_node_for_deterministic_datetime(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "message_type": "business_question",
                    "context_usage": "none",
                    "intent": "daily_tool",
                    "route": "tool",
                    "standalone_query": "现在上海时间是多少？",
                    "risk_level": "low",
                    "selected_tool": "get_current_datetime",
                    "selected_action": "*",
                    "time_requirement": {"time_reference_type": "relative", "requires_current_datetime": True},
                    "knowledge_requirement": {"requires_company_knowledge": False, "should_use_rag": False},
                    "reason": "查询当前时间",
                },
                ensure_ascii=False,
            )
        ]
    )
    workflow = AgenticRAGWorkflow(make_settings(tmp_path), llm=llm)
    workflow._compiled = None

    state = workflow.run("现在上海时间是多少？", role="employee")

    node_names = [item["node"] for item in state["node_trace"]]
    assert "classify_intent" in node_names
    assert "build_plan" not in node_names
    assert "validate_plan" in node_names
    assert [call["node"] for call in state["llm_calls"]] == ["classify_intent"]
