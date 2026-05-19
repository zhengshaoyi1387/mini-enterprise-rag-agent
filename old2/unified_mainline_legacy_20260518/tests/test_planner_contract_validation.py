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


def test_current_datetime_requirement_becomes_datetime_tool_task(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("现在的日期和时间", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "direct",
        "route": "direct",
        "standalone_query": "现在的日期和时间",
        "knowledge_requirement": {"requires_company_knowledge": False, "should_use_rag": False},
        "time_requirement": {"time_reference_type": "relative", "requires_current_datetime": True},
        "execution_plan": {"tasks": [], "strategy": "short"},
        "reason": "获取当前时间",
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "tool"
    assert state["intent"] == "daily_tool"
    assert state["selected_tool"] == "get_current_datetime"
    assert state["selected_action"] == "*"
    assert state["current_task"]["tool"] == "get_current_datetime"
    assert state["current_task"]["tool_input"]["timezone"] == "Asia/Shanghai"
    assert state["plan_validation"]["normalization_reason"] == "current datetime requires get_current_datetime tool"


def test_missing_calendar_create_slots_are_clarification_before_tool(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("创建一个公司会议。", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": "创建一个公司会议。",
        "selected_tool": "manage_company_calendar",
        "selected_action": "create",
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "create_calendar",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "create",
                    "tool_input": {"action": "create", "title": "公司会议", "type": "meeting"},
                }
            ]
        },
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "direct"
    assert state["intent"] in {"need_clarification", "clarification_required"}
    assert state["execution_plan"]["tasks"] == []
    assert state["plan_validation"]["validation_status"] == "needs_clarification"


def test_query_first_plan_does_not_hide_ambiguous_calendar_write_intent(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    question = "把那个会议改成 10 点。"
    classification = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": question,
        "selected_tool": "manage_company_calendar",
        "selected_action": "update",
        "time_requirement": {"time_reference_type": "ambiguous", "requires_current_datetime": False},
        "knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False},
    }
    plan = {
        "missing_required_slots": ["event_id"],
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": "查询当前日历中符合会议的事件",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
                }
            ]
        },
    }

    state = create_initial_state(question, role="admin")
    state["raw_plan"] = nodes._merge_classification_and_plan(classification, plan, question)
    state = nodes.validate_plan(state)

    assert state["route"] == "direct"
    assert state["intent"] == "need_clarification"
    assert state["execution_plan"]["tasks"] == []


def test_query_first_update_request_completes_missing_update_task(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    question = "先查 2026-05-24 的培训日程，再把第一个培训地点改成线上会议室。"
    state = create_initial_state(question, role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": question,
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "time_requirement": {"time_reference_type": "absolute", "absolute_date": "2026-05-24", "requires_current_datetime": False},
        "knowledge_requirement": {"requires_company_knowledge": False, "should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": "查询 2026-05-24 的培训日程",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {
                        "action": "query",
                        "event_type": "training",
                        "start_date": "2026-05-24",
                        "end_date": "2026-05-24",
                        "department": "all",
                    },
                }
            ]
        },
    }

    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["action"] for task in tasks] == ["query", "update"]
    assert tasks[1]["tool_input"]["location"] == "线上会议室"
    assert tasks[1]["tool_input"]["selector"]["ordinal"] == "first"
    assert tasks[1]["tool_input"]["selector"]["event_type"] == "training"


def test_absolute_date_literal_in_task_text_becomes_executable_calendar_query(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    question = "2026-05-24 有哪些培训？"
    state = create_initial_state(question, role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": question,
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "time_requirement": {"time_reference_type": "absolute", "requires_current_datetime": True},
        "knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "training_query",
                    "kind": "tool",
                    "objective": "查询 2026-05-24 的培训日程",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "training", "department": "all"},
                }
            ]
        },
    }

    state = nodes.validate_plan(state)
    task = state["execution_plan"]["tasks"][0]
    payload = nodes._build_tool_payload(state, "manage_company_calendar", "employee")

    assert task["time_requirement"]["time_reference_type"] == "absolute"
    assert task["time_requirement"]["absolute_date"] == "2026-05-24"
    assert task["time_requirement"]["requires_current_datetime"] is False
    assert payload["start_date"] == "2026-05-24"
    assert payload["end_date"] == "2026-05-24"


def test_calendar_write_ability_question_needs_confirmation_before_write(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("能不能把明天会议改到 10 点？", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "manage_company_calendar",
        "selected_action": "update",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "tomorrow", "requires_current_datetime": True},
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {"task_id": "q", "kind": "tool", "tool": "manage_company_calendar", "action": "query", "tool_input": {"action": "query"}},
                {
                    "task_id": "u",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "tool_input": {"action": "update", "selector": {"event_type": "meeting"}, "time": "10:00-10:00"},
                },
            ]
        },
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "direct"
    assert state["intent"] == "need_clarification"
    assert state["execution_plan"]["tasks"] == []


def test_mixed_datetime_multiple_calendar_relative_queries_are_completed(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    question = "先告诉我今天日期，再查明天的会议和后天的培训。"
    state = create_initial_state(question, role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": question,
        "selected_tool": "get_current_datetime",
        "selected_action": "*",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "today", "requires_current_datetime": True},
        "knowledge_requirement": {"requires_company_knowledge": False, "should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": question,
                    "tool": "get_current_datetime",
                    "action": "*",
                    "tool_input": {"timezone": "Asia/Shanghai"},
                    "time_requirement": {"time_reference_type": "relative", "canonical_relative": "today", "requires_current_datetime": True},
                }
            ]
        },
    }

    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["tool"] for task in tasks] == ["get_current_datetime", "manage_company_calendar", "manage_company_calendar"]
    assert tasks[1]["tool_input"]["event_type"] == "meeting"
    assert tasks[1]["time_requirement"]["canonical_relative"] == "tomorrow"
    assert tasks[2]["tool_input"]["event_type"] == "training"
    assert tasks[2]["time_requirement"]["canonical_relative"] == "day_after_tomorrow"


def test_absolute_task_date_is_not_overwritten_by_root_relative_time(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("查询上周请假汇总，再查询 2026-05-12 研发部缺勤记录。", role="hr")
    state["raw_plan"] = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": "查询上周请假汇总，再查询 2026-05-12 研发部缺勤记录。",
        "selected_tool": "query_attendance_summary",
        "selected_action": "query",
        "time_requirement": {
            "time_reference_type": "relative",
            "canonical_relative": "last_week",
            "requires_current_datetime": True,
        },
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "summary",
                    "kind": "tool",
                    "tool": "query_attendance_summary",
                    "action": "query",
                    "tool_input": {"status_filter": "leave", "group_by": "department"},
                },
                {
                    "task_id": "detail",
                    "kind": "tool",
                    "tool": "query_attendance_summary",
                    "action": "query",
                    "objective": "查询 2026-05-12 研发部缺勤记录",
                    "tool_input": {
                        "start_date": "2026-05-12",
                        "end_date": "2026-05-12",
                        "department": "研发部",
                        "status_filter": "absent",
                        "include_records": True,
                    },
                },
            ]
        },
    }

    state = nodes.validate_plan(state)
    tasks = state["execution_plan"]["tasks"]

    assert tasks[0]["time_requirement"]["canonical_relative"] == "last_week"
    assert tasks[1]["tool_input"]["start_date"] == "2026-05-12"
    assert tasks[1]["tool_input"]["end_date"] == "2026-05-12"
    assert tasks[1]["time_requirement"]["time_reference_type"] == "range"


def test_task_text_relative_month_overrides_planner_guessed_absolute_range(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("统计 2026 年 5 月迟到员工明细，并告诉我产品部本月有哪些异常。", role="hr")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "query_attendance_summary",
        "selected_action": "query",
        "time_requirement": {"time_reference_type": "absolute", "requires_current_datetime": False},
        "knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "product_anomaly",
                    "kind": "tool",
                    "objective": "查询产品部本月异常考勤情况（迟到/请假/缺勤）",
                    "tool": "query_attendance_summary",
                    "action": "query",
                    "tool_input": {
                        "start_date": "2024-06-01",
                        "end_date": "2024-06-30",
                        "department": "产品部",
                        "status_filters": ["late", "leave", "absent"],
                    },
                }
            ]
        },
    }

    state = nodes.validate_plan(state)
    task = state["execution_plan"]["tasks"][0]

    assert task["time_requirement"]["canonical_relative"] == "this_month"
    assert task["time_requirement"]["requires_current_datetime"] is True
    assert "start_date" not in task["tool_input"]
    assert "end_date" not in task["tool_input"]


def test_employee_department_attendance_detail_is_refused_before_tool(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("帮我查一下产品部 2026 年 5 月考勤异常明细。", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "query_attendance_summary",
        "selected_action": "query",
        "time_requirement": {"time_reference_type": "absolute", "requires_current_datetime": False},
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "attendance_detail",
                    "kind": "tool",
                    "objective": "查询产品部 2026 年 5 月考勤异常明细",
                    "tool": "query_attendance_summary",
                    "action": "query",
                    "tool_input": {
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-31",
                        "department": "产品部",
                        "group_by": "employee",
                        "status_filters": ["late", "leave", "absent"],
                        "include_records": True,
                    },
                }
            ]
        },
    }

    state = nodes.validate_plan(state)
    state = nodes.generate_answer(state)

    assert state["route"] == "direct"
    assert state["intent"] == "permission_required"
    assert state["execution_plan"]["tasks"] == []
    assert state["tool_calls"] == []
    assert "HR" in state["final_answer"]
    assert "权限" in state["final_answer"]


def test_employee_named_attendance_query_remains_executable(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("查询张三今天的考勤状态。", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "query_attendance_summary",
        "selected_action": "query",
        "time_requirement": {"time_reference_type": "absolute", "requires_current_datetime": False},
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "personal_attendance",
                    "kind": "tool",
                    "objective": "查询张三今天的考勤状态",
                    "tool": "query_attendance_summary",
                    "action": "query",
                    "tool_input": {
                        "start_date": "2026-05-16",
                        "end_date": "2026-05-16",
                        "employee_name": "张三",
                        "group_by": "employee",
                        "include_records": True,
                    },
                }
            ]
        },
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "tool"
    assert state["selected_tool"] == "query_attendance_summary"
    assert state["execution_plan"]["tasks"][0]["tool_input"]["employee_name"] == "张三"


def test_symbolic_calendar_date_placeholder_becomes_time_requirement(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("查明天会议。", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": "查明天会议。",
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "calendar_query",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {
                        "action": "query",
                        "start_date": "${tomorrow}",
                        "end_date": "${tomorrow}",
                        "event_type": "meeting",
                        "department": "all",
                    },
                }
            ]
        },
    }

    state = nodes.validate_plan(state)
    task = state["execution_plan"]["tasks"][0]

    assert state["route"] == "tool"
    assert task["time_requirement"]["canonical_relative"] == "tomorrow"
    assert "start_date" not in task["tool_input"]
    assert "end_date" not in task["tool_input"]
