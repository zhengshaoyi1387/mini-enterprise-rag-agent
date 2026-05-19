from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from mini_rag.agent.context_store import SQLiteContextStore
from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state


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
        return FakeMessage("工具结果回答")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def write_attendance(path: Path) -> None:
    rows = [
        ["date", "employee_id", "name", "department", "status", "check_in", "check_out"],
        ["2026-05-07", "u001", "张三", "Engineering", "present", "09:02", "18:10"],
        ["2026-05-07", "u002", "李四", "Engineering", "late", "09:35", "18:05"],
        ["2026-05-07", "u003", "王五", "Sales", "leave", "", ""],
        ["2026-05-07", "u004", "赵六", "HR", "present", "09:00", "18:00"],
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def fake_datetime(_payload):
    return {
        "current_date": "2026-05-08",
        "current_time": "10:00:00",
        "weekday": "Friday",
        "timezone": "Asia/Shanghai",
        "ranges": {
            "today": {"start_date": "2026-05-08", "end_date": "2026-05-08"},
            "yesterday": {"start_date": "2026-05-07", "end_date": "2026-05-07"},
            "tomorrow": {"start_date": "2026-05-09", "end_date": "2026-05-09"},
            "next_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
        },
    }


def test_understand_query_calls_llm_for_daily_tool(tmp_path: Path) -> None:
    llm = RecordingLLM([
        json.dumps(
            {
                "intent": "daily_tool",
                "route": "tool",
                "standalone_query": "查询昨天公司的出勤情况",
                "topic": "attendance",
                "entities": [],
                "risk_level": "medium",
                "selected_tool": "query_attendance_summary",
                "required_tools": ["query_attendance_summary"],
                "tool_input": {"department": "all", "group_by": "department"},
                "needs_time_resolution": True,
                "relative_time": "yesterday",
                "missing_required_slots": [],
                "reason": "需要考勤工具",
            },
            ensure_ascii=False,
        )
    ])
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("昨天公司的出勤情况如何？", role="employee")

    state = nodes.understand_query(state)

    assert len(llm.calls) == 1
    assert state["candidate_tool"] is None
    assert state["selected_tool"] == "query_attendance_summary"
    assert state["needs_time_resolution"] is True
    assert state["relative_time"] == "yesterday"


def test_rule_candidate_does_not_override_llm(tmp_path: Path) -> None:
    llm = RecordingLLM([
        json.dumps(
            {
                "intent": "direct",
                "route": "direct",
                "standalone_query": "解释考勤系统这个词",
                "topic": "general",
                "entities": [],
                "risk_level": "low",
                "selected_tool": None,
                "required_tools": [],
                "tool_input": {},
                "needs_time_resolution": False,
                "relative_time": None,
                "missing_required_slots": [],
                "reason": "LLM 判断无需工具",
            },
            ensure_ascii=False,
        )
    ])
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("解释一下考勤这个词", role="employee")

    state = nodes.understand_query(state)
    state = nodes.route(state)

    assert state["candidate_tool"] is None
    assert state["route"] == "direct"
    assert state["selected_tool"] is None


def test_previous_tool_context_is_loaded_into_understand_prompt(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = SQLiteContextStore(settings.context_db_path)
    previous_context = {
        "domain": "attendance",
        "tool_name": "query_attendance_summary",
        "tool_input": {"start_date": "2026-05-07", "end_date": "2026-05-07", "department": "all"},
        "result_summary": "2026-05-07 至 2026-05-07 的考勤汇总：记录 4 条。",
    }
    store.append_turn(
        session_id="s1",
        question="昨天公司的出勤情况如何？",
        standalone_query="查询 2026-05-07 公司出勤",
        answer="汇总回答",
        sources=[],
        trace={"current_tool_context": previous_context},
    )
    llm = RecordingLLM([
        json.dumps(
            {
                "intent": "daily_tool",
                "route": "tool",
                "standalone_query": "查询 2026-05-07 公司迟到人员",
                "topic": "attendance",
                "entities": [],
                "risk_level": "medium",
                "selected_tool": "query_attendance_summary",
                "required_tools": ["query_attendance_summary"],
                "tool_input": {
                    "start_date": "2026-05-07",
                    "end_date": "2026-05-07",
                    "department": "all",
                    "group_by": "employee",
                    "status_filter": "late",
                    "include_records": True,
                },
                "needs_time_resolution": False,
                "relative_time": None,
                "missing_required_slots": [],
                "reason": "追问上一轮考勤",
            },
            ensure_ascii=False,
        )
    ])
    nodes = AgenticRAGNodes(settings, llm=llm)
    nodes.context_store = store
    state = create_initial_state("谁迟到了？", session_id="s1", role="employee")

    state = nodes.load_context(state)
    state = nodes.understand_query(state)

    prompt = llm.calls[0][-1][1]
    assert state["previous_tool_context"] == previous_context
    assert "previous_tool_context" in prompt
    assert "2026-05-07" in prompt


def test_followup_attendance_tool_plan_uses_previous_context(tmp_path: Path) -> None:
    attendance_path = tmp_path / "attendance.csv"
    write_attendance(attendance_path)
    llm = RecordingLLM([])
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("谁迟到了？", role="employee")
    state.update(
        {
            "route": "tool",
            "selected_tool": "query_attendance_summary",
            "required_tools": ["query_attendance_summary"],
            "tool_input": {
                "start_date": "2026-05-07",
                "end_date": "2026-05-07",
                "department": "all",
                "group_by": "employee",
                "status_filter": "late",
                "include_records": True,
                "file_path": str(attendance_path),
            },
        }
    )

    state = nodes.call_tool(state)

    attendance_call = [call for call in state["tool_calls"] if call["tool_name"] == "query_attendance_summary"][-1]
    assert attendance_call["args"]["start_date"] == "2026-05-07"
    assert attendance_call["args"]["end_date"] == "2026-05-07"
    assert attendance_call["args"]["status_filter"] == "late"
    assert attendance_call["args"]["include_records"] is True
    assert "invalid date format" not in json.dumps(state, ensure_ascii=False)
    assert state["tool_result"]["records"][0]["name"] == "李四"


def test_relative_time_attendance_uses_datetime_then_attendance(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    attendance_path = tmp_path / "attendance.csv"
    write_attendance(attendance_path)
    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("昨天公司的出勤情况如何？", role="employee")
    state.update(
        {
            "route": "tool",
            "selected_tool": "query_attendance_summary",
            "required_tools": ["query_attendance_summary"],
            "tool_input": {"department": "all", "group_by": "department", "file_path": str(attendance_path)},
            "needs_time_resolution": True,
            "relative_time": "yesterday",
        }
    )

    state = nodes.call_tool(state)

    names = [call["tool_name"] for call in state["tool_calls"]]
    assert "get_current_datetime" in names
    args = [call for call in state["tool_calls"] if call["tool_name"] == "query_attendance_summary"][-1]["args"]
    assert args["start_date"] == "2026-05-07"
    assert args["end_date"] == "2026-05-07"
    assert re.match(r"\d{4}-\d{2}-\d{2}", args["start_date"])


def test_tool_error_not_exposed_to_user(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("谁迟到了？", role="employee")
    state.update(
        {
            "route": "tool",
            "selected_tool": "query_attendance_summary",
            "required_tools": ["query_attendance_summary"],
            "tool_input": {"department": "all", "group_by": "employee", "status_filter": "late", "include_records": True},
        }
    )

    state = nodes.call_tool(state)

    assert "invalid date format" not in state["final_answer"]
    assert "明确的日期范围" in state["final_answer"]


def test_calendar_relative_time_query(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    calendar_path = tmp_path / "company_calendar.json"
    calendar_path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260513-0001",
                    "date": "2026-05-13",
                    "title": "新员工培训",
                    "type": "training",
                    "department": "all",
                    "time": "14:00-16:00",
                    "location": "会议室 A",
                    "description": "面向本月入职员工",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("下周公司有哪些安排？", role="employee")
    state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {"action": "query", "department": "all", "event_type": "all", "file_path": str(calendar_path)},
            "needs_time_resolution": True,
            "relative_time": "next_week",
        }
    )

    state = nodes.call_tool(state)

    args = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]["args"]
    assert args["start_date"] == "2026-05-11"
    assert args["end_date"] == "2026-05-17"
    assert state["tool_result"]["events"][0]["title"] == "新员工培训"


def test_calendar_write_permission_still_admin_only(tmp_path: Path) -> None:
    calendar_path = tmp_path / "company_calendar.json"
    calendar_path.write_text("[]", encoding="utf-8")
    employee_nodes = AgenticRAGNodes(make_settings(tmp_path / "employee"), llm=RecordingLLM([]))
    employee_state = create_initial_state("帮我添加一个会议", role="employee")
    employee_state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {
                "action": "create",
                "date": "2026-05-09",
                "title": "全员会",
                "type": "meeting",
                "time": "15:00",
                "file_path": str(calendar_path),
            },
        }
    )

    employee_state = employee_nodes.call_tool(employee_state)
    assert "没有权限修改公司日程" in employee_state["final_answer"]

    admin_nodes = AgenticRAGNodes(make_settings(tmp_path / "admin"), llm=RecordingLLM([]))
    admin_state = create_initial_state("帮我添加一个会议", role="admin")
    admin_state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {
                "action": "create",
                "date": "2026-05-09",
                "title": "全员会",
                "type": "meeting",
                "time": "15:00",
                "file_path": str(calendar_path),
            },
        }
    )

    admin_state = admin_nodes.call_tool(admin_state)
    assert admin_state["tool_result"]["status"] == "created"


def test_current_tool_context_saved_to_trace(tmp_path: Path) -> None:
    attendance_path = tmp_path / "attendance.csv"
    write_attendance(attendance_path)
    settings = make_settings(tmp_path)
    store = SQLiteContextStore(settings.context_db_path)
    nodes = AgenticRAGNodes(settings, llm=RecordingLLM([]))
    nodes.context_store = store
    state = create_initial_state("谁迟到了？", session_id="s1", role="employee")
    state.update(
        {
            "route": "tool",
            "selected_tool": "query_attendance_summary",
            "required_tools": ["query_attendance_summary"],
            "tool_input": {
                "start_date": "2026-05-07",
                "end_date": "2026-05-07",
                "department": "all",
                "group_by": "employee",
                "status_filter": "late",
                "include_records": True,
                "file_path": str(attendance_path),
            },
            "final_answer": "昨天共有 1 人迟到：李四。",
        }
    )

    state = nodes.call_tool(state)
    trace = nodes.build_trace(state)
    store.append_turn("s1", "谁迟到了？", "查询 2026-05-07 迟到人员", "昨天共有 1 人迟到：李四。", [], trace)
    next_nodes = AgenticRAGNodes(settings, llm=RecordingLLM([]))
    next_nodes.context_store = store
    next_state = create_initial_state("他几点打卡？", session_id="s1", role="employee")
    next_state = next_nodes.load_context(next_state)

    assert trace["current_tool_context"]["tool_name"] == "query_attendance_summary"
    assert next_state["previous_tool_context"]["tool_input"]["status_filter"] == "late"
