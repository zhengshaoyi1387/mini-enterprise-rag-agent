from __future__ import annotations

import json
from pathlib import Path

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class NoopLLM:
    def __init__(self):
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return FakeMessage("{}")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_followup_previous_calendar_context_cannot_stay_direct(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("下下周呢", role="admin")
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {
            "action": "query",
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "query_scope": "all_events",
            "event_type": "all",
            "department": "all",
        },
        "result_summary": "2026-05-11 至 2026-05-17 的公司日程：...",
    }
    state["raw_plan"] = {
        "message_type": "followup_question",
        "context_usage": "use_previous_tool_context",
        "intent": "direct",
        "route": "direct",
        "standalone_query": "下下周呢",
        "selected_tool": None,
        "selected_action": None,
        "tool_input": {},
        "time_requirement": {
            "has_time_requirement": True,
            "time_reference_type": "relative",
            "canonical_relative": "week_after_next",
            "requires_current_datetime": True,
        },
        "knowledge_requirement": {"should_use_rag": False},
        "reason": "延续上轮日程查询",
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "tool"
    assert state["intent"] == "daily_tool"
    assert state["selected_tool"] == "manage_company_calendar"
    assert state["selected_action"] == "query"
    assert state["tool_input"]["query_scope"] == "all_events"
    assert state["tool_input"]["event_type"] == "all"
    assert state["relative_time"] == "week_after_next"


def test_week_after_next_calendar_query_uses_datetime_tool(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    def fake_datetime(_payload):
        return {
            "current_date": "2026-05-10",
            "current_time": "10:00:00",
            "weekday": "Sunday",
            "timezone": "Asia/Shanghai",
            "ranges": {
                "week_after_next": {"start_date": "2026-05-18", "end_date": "2026-05-24"},
            },
        }

    calendar_path = tmp_path / "company_calendar.json"
    calendar_path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260518-0001",
                    "date": "2026-05-18",
                    "title": "下下周例会",
                    "type": "meeting",
                    "department": "all",
                    "time": "10:00-11:00",
                    "location": "线上",
                    "description": "",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("下下周呢", role="admin")
    state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "selected_action": "query",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {
                "action": "query",
                "query_scope": "all_events",
                "event_type": "all",
                "department": "all",
                "file_path": str(calendar_path),
            },
            "time_reference": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "week_after_next",
                "requires_current_datetime": True,
                "needs_current_datetime": True,
            },
            "needs_time_resolution": True,
            "relative_time": "week_after_next",
        }
    )

    state = nodes.call_tool(state)

    names = [call["tool_name"] for call in state["tool_calls"]]
    assert "get_current_datetime" in names
    calendar_call = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]
    assert calendar_call["args"]["start_date"] == "2026-05-18"
    assert calendar_call["args"]["end_date"] == "2026-05-24"
    assert state["tool_result"]["events"][0]["title"] == "下下周例会"
