from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

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
        return FakeMessage("LLM fallback answer")


class RecordingRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, **_kwargs):
        self.queries.append(query)
        return (
            [
                Document(
                    page_content="报销制度要求发票真实有效，抬头、税号、金额、日期等信息应完整准确。",
                    metadata={"source": "finance.md", "title_path": "发票要求", "chunk_id": "fin-1", "rank": 1},
                )
            ],
            {"query": query, "result_count": 1, "results": [{"source": "finance.md", "chunk_id": "fin-1"}]},
        )


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
        AGENT_COMPLETION_MAX_REPLANS=2,
    )


def calendar_path(tmp_path: Path) -> Path:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260512-0001",
                    "date": "2026-05-12",
                    "title": "产品评审会",
                    "type": "meeting",
                    "department": "all",
                    "time": "10:00-11:00",
                    "location": "会议室A",
                    "description": "产品计划评审",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def fake_datetime(_payload):
    return {
        "current_date": "2026-05-09",
        "current_time": "10:00:00",
        "weekday": "Saturday",
        "timezone": "Asia/Shanghai",
        "ranges": {
            "today": {"start_date": "2026-05-09", "end_date": "2026-05-09"},
            "tomorrow": {"start_date": "2026-05-10", "end_date": "2026-05-10"},
            "this_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"},
            "next_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
        },
    }


def plan_payload(*, tasks: list[dict], route: str = "tool", selected_tool: str | None = None, selected_action: str | None = None) -> str:
    payload = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "daily_tool" if route == "tool" else "rag_fact",
        "route": route,
        "standalone_query": "复合企业任务",
        "topic": "enterprise_task",
        "entities": [],
        "risk_level": "medium",
        "selected_tool": selected_tool,
        "selected_action": selected_action,
        "tool_input": {},
        "time_requirement": {
            "has_time_requirement": False,
            "time_reference_type": "none",
            "canonical_relative": None,
            "absolute_date": None,
            "date_range": None,
            "requires_current_datetime": False,
        },
        "knowledge_requirement": {"requires_company_knowledge": False, "known_from_user_message": True, "should_use_rag": route == "rag"},
        "execution_plan": {"tasks": tasks},
        "missing_required_slots": [],
        "reason": "多任务规划",
    }
    return json.dumps(payload, ensure_ascii=False)


def ready_reflection() -> str:
    return json.dumps(
        {
            "ready_to_answer": True,
            "completed_objectives": ["全部完成"],
            "missing_objectives": [],
            "unsupported_parts": [],
            "next_action": "answer",
            "followup_tasks": [],
            "reason": "任务已完成",
        },
        ensure_ascii=False,
    )


def build_workflow(tmp_path: Path, llm: RecordingLLM, retriever: RecordingRetriever | None = None) -> AgenticRAGWorkflow:
    workflow = AgenticRAGWorkflow(make_settings(tmp_path), llm=llm, retriever=retriever)
    workflow._compiled = None
    return workflow


def test_compound_calendar_create_then_query_executes_both_and_templates_answer(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    tasks = [
        {
            "task_id": "t1",
            "kind": "tool",
            "objective": "新增下周三员工培训日程",
            "tool": "manage_company_calendar",
            "action": "create",
            "tool_input": {
                "action": "create",
                "title": "员工培训",
                "type": "training",
                "time": "09:00-11:00",
                "department": "all",
                "location": "会议室B",
                "file_path": str(path),
            },
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "next_week",
                "requires_current_datetime": True,
            },
        },
        {
            "task_id": "t2",
            "kind": "tool",
            "objective": "查询下周公司日程安排",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "next_week",
                "requires_current_datetime": True,
            },
            "depends_on": ["t1"],
        },
    ]
    llm = RecordingLLM(
        [
            plan_payload(tasks=tasks, route="tool", selected_tool="manage_company_calendar", selected_action="create"),
            json.dumps(
                {
                    "action": "create",
                    "title": "员工培训",
                    "type": "training",
                    "date": "2026-05-13",
                    "time": "09:00-11:00",
                    "department": "all",
                    "location": "会议室B",
                    "file_path": str(path),
                },
                ensure_ascii=False,
            ),
            "已新增员工培训，并查询到下周公司日程包含产品评审会和员工培训。",
        ]
    )
    state = build_workflow(tmp_path, llm).run("帮我新增一个公司日程，时间下周三早上九点到十一点，地点会议室B，内容是员工培训。然后告诉我公司下周的日程安排。", role="admin")

    calendar_calls = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"]
    assert [call["action"] for call in calendar_calls] == ["create", "query"]
    assert [result["task_id"] for result in state["task_results"]] == ["t1", "t2"]
    assert "员工培训" in state["final_answer"]
    assert "产品评审会" in state["final_answer"]
    assert not any(call["node"] == "completion_reflect" for call in state["llm_calls"])
    assert not any(call["node"] == "generate_answer" for call in state["llm_calls"])


def test_mixed_calendar_and_rag_tasks_both_feed_final_answer(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    tasks = [
        {
            "task_id": "calendar",
            "kind": "tool",
            "objective": "查询下周公司日程",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "next_week",
                "requires_current_datetime": True,
            },
        },
        {
            "task_id": "policy",
            "kind": "rag",
            "objective": "查询公司报销制度",
            "query": "公司的报销制度里对发票有什么要求？",
        },
    ]
    llm = RecordingLLM(
        [
            plan_payload(tasks=tasks, route="tool", selected_tool="manage_company_calendar", selected_action="query"),
            "下周公司有产品评审会；报销制度要求发票真实有效且信息完整。",
        ]
    )
    retriever = RecordingRetriever()
    state = build_workflow(tmp_path, llm, retriever=retriever).run("公司下周的日程安排和公司的报销制度里对发票有什么要求？", role="admin")

    assert any(call["tool_name"] == "manage_company_calendar" for call in state["tool_calls"])
    assert any(call["tool_name"] == "search_knowledge_base" for call in state["tool_calls"])
    assert retriever.queries == ["公司的报销制度里对发票有什么要求？"]
    assert {result["task_id"] for result in state["task_results"]} == {"calendar", "policy"}
    assert "产品评审会" in state["final_answer"]
    assert "发票真实有效" in state["final_answer"]


def test_calendar_update_selector_resolves_event_type_date_range_and_first(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("把下周第一个团建改成公司高层会议", role="admin")
    state["task_results"] = [
        {
            "task_id": "t1",
            "kind": "tool",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "event_type": "activity"},
            "tool_result": {
                "events": [
                    {
                        "event_id": "EVT-20260519-0001",
                        "date": "2026-05-19",
                        "title": "公司团建",
                        "type": "activity",
                        "department": "all",
                        "time": "16:00-18:00",
                    },
                    {
                        "event_id": "EVT-20260521-0002",
                        "date": "2026-05-21",
                        "title": "公司团建",
                        "type": "activity",
                        "department": "all",
                        "time": "18:00-20:00",
                    },
                ]
            },
        }
    ]
    state["task_queue"] = [
        {
            "task_id": "t2",
            "kind": "tool",
            "objective": "更新第一个团建",
            "tool": "manage_company_calendar",
            "action": "update",
            "tool_input": {
                "action": "update",
                "selector": {
                    "event_type": "activity",
                    "date_range": {"start_date": "2026-05-18", "end_date": "2026-05-24"},
                    "ordinal": "first",
                },
                "title": "公司高层会议",
                "time": "21:00-22:00",
            },
        }
    ]

    changed = nodes._resolve_calendar_update_tasks(state)

    assert changed is True
    assert state["task_queue"][0]["tool_input"]["event_id"] == "EVT-20260519-0001"
    assert state["task_queue"][0]["tool_input"]["title"] == "公司高层会议"


def test_calendar_delete_empty_query_skips_without_calling_placeholder_event_id(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("删除 2099-01-01 的所有公司会议", role="admin")
    state["task_results"] = [
        {
            "task_id": "t1",
            "kind": "tool",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "event_type": "meeting"},
            "tool_result": {"events": []},
        }
    ]
    state["task_queue"] = [
        {
            "task_id": "t2",
            "kind": "tool",
            "objective": "删除查询到的会议",
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "event_id": "multiple"},
        }
    ]

    changed = nodes._resolve_calendar_delete_tasks(state)

    assert changed is True
    assert state["task_queue"] == []
    assert state["task_results"][-1]["status"] == "skipped"
    assert state["task_results"][-1]["result_summary"] == "没有匹配日程可删除，无需删除。"


def test_calendar_delete_multiple_matches_without_selector_requires_clarification(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("删除 2026-05-18 的公司会议。", role="admin")
    state["task_results"] = [
        {
            "task_id": "t1",
            "kind": "tool",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "event_type": "meeting"},
            "tool_result": {
                "events": [
                    {"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting"},
                    {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting"},
                ]
            },
        }
    ]
    state["task_queue"] = [
        {
            "task_id": "t2",
            "kind": "tool",
            "objective": "删除查询到的会议",
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "event_id": "EVT-20260518-XXXX"},
        }
    ]

    changed = nodes._resolve_calendar_delete_tasks(state)

    assert changed is True
    assert state["task_queue"] == []
    result = state["task_results"][-1]
    assert result["status"] == "needs_clarification"
    assert result["tool_result"]["candidate_events"][0]["event_id"] == "EVT-20260518-0001"
    assert result["tool_result"]["candidate_events"][1]["event_id"] == "EVT-20260518-0002"


def test_calendar_delete_selector_merges_all_from_objective(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("删除下周所有公司团建。", role="admin")
    state["task_results"] = [
        {
            "task_id": "query_calendar",
            "kind": "tool",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_input": {
                "action": "query",
                "start_date": "2026-05-18",
                "end_date": "2026-05-24",
                "event_type": "activity",
            },
            "tool_result": {
                "events": [
                    {"event_id": "EVT-20260519-0001", "date": "2026-05-19", "title": "公司团建", "type": "activity"},
                    {"event_id": "EVT-20260521-0002", "date": "2026-05-21", "title": "公司团建", "type": "activity"},
                ]
            },
        }
    ]
    state["task_queue"] = [
        {
            "task_id": "delete_calendar",
            "kind": "tool",
            "objective": "删除下周所有公司团建",
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "selector": {"event_type": "activity"}},
        }
    ]

    changed = nodes._resolve_calendar_delete_tasks(state)

    assert changed is True
    assert [task["tool_input"]["event_id"] for task in state["task_queue"]] == [
        "EVT-20260519-0001",
        "EVT-20260521-0002",
    ]
    assert all(task["tool_input"]["action"] == "delete" for task in state["task_queue"])


def test_task_time_requirement_does_not_inherit_top_level_today(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("现在日期时间，顺便查明天会议", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": "现在日期时间，顺便查明天会议",
        "selected_tool": "get_current_datetime",
        "selected_action": "*",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "today", "requires_current_datetime": True},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": "获取当前日期时间",
                    "tool": "get_current_datetime",
                    "action": "*",
                    "tool_input": {"timezone": "Asia/Shanghai"},
                    "time_requirement": {"time_reference_type": "relative", "canonical_relative": "today", "requires_current_datetime": True},
                },
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "objective": "查询明天会议",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
                },
            ]
        },
    }

    state = nodes.validate_plan(state)
    second = state["execution_plan"]["tasks"][1]

    assert second["time_requirement"]["time_reference_type"] == "relative"
    assert second["time_requirement"]["canonical_relative"] == "tomorrow"
    assert second["time_requirement"]["requires_current_datetime"] is True


def test_top_level_relative_repairs_date_dependent_calendar_query_task(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("先查下周所有公司团建日程，再把第一个改成公司高层会议", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "next_week", "requires_current_datetime": True},
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": "查询下周所有公司团建日程",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "activity", "department": "all"},
                },
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "objective": "更新第一个团建",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "tool_input": {
                        "action": "update",
                        "selector": {"event_type": "activity", "ordinal": 1},
                        "title": "公司高层会议",
                    },
                },
            ]
        },
    }

    state = nodes.validate_plan(state)

    first = state["execution_plan"]["tasks"][0]
    assert first["time_requirement"]["canonical_relative"] == "next_week"
    assert first["time_requirement"]["requires_current_datetime"] is True
    second = state["execution_plan"]["tasks"][1]
    assert second["time_requirement"]["time_reference_type"] == "none"


def test_symbolic_calendar_query_dates_are_converted_to_task_time_requirement(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("现在日期时间是多少？顺便查一下明天的公司会议安排。", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "get_current_datetime",
        "selected_action": "*",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "tomorrow", "requires_current_datetime": True},
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {"task_id": "t1", "kind": "tool", "tool": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}},
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "objective": "查询明天公司会议",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "start_date": "today", "end_date": "tomorrow"},
                },
            ]
        },
    }

    state = nodes.validate_plan(state)

    second = state["execution_plan"]["tasks"][1]
    assert second["time_requirement"]["canonical_relative"] == "tomorrow"
    assert second["time_requirement"]["requires_current_datetime"] is True
    assert "start_date" not in second["tool_input"]
    assert "end_date" not in second["tool_input"]


def test_calendar_query_today_offset_dates_are_resolved_with_datetime_tool(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    def fixed_datetime(_payload):
        return {
            "current_date": "2026-05-17",
            "current_time": "09:00:00",
            "weekday": "Sunday",
            "timezone": "Asia/Shanghai",
            "ranges": {
                "today": {"start_date": "2026-05-17", "end_date": "2026-05-17"},
                "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"},
                "day_after_tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"},
            },
        }

    monkeypatch.setattr(nodes_module, "get_current_datetime", fixed_datetime)
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("先告诉我今天日期，再查明天的会议和后天的培训。", role="employee")
    state["selected_tool"] = "manage_company_calendar"
    state["selected_action"] = "query"
    state["tool_input"] = {
        "action": "query",
        "event_type": "training",
        "start_date": "today + 2 days",
        "end_date": "today + 2 days",
    }
    state["time_requirement"] = {
        "has_time_requirement": False,
        "time_reference_type": "none",
        "canonical_relative": None,
        "absolute_date": None,
        "date_range": None,
        "requires_current_datetime": False,
    }

    payload = nodes._build_tool_payload(state, "manage_company_calendar", "employee")

    assert payload["start_date"] == "2026-05-19"
    assert payload["end_date"] == "2026-05-19"
    assert state["tool_calls"][-1]["tool_name"] == "get_current_datetime"


def test_symbolic_query_dates_do_not_override_non_today_root_time_requirement(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("现在的日期时间是多少？顺便查一下明天的公司会议安排。", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "get_current_datetime",
        "selected_action": "*",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "tomorrow", "requires_current_datetime": True},
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {"task_id": "t1", "kind": "tool", "tool": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}},
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "objective": "查询明天的公司会议安排",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "start_date": "today", "end_date": "today"},
                },
            ]
        },
    }

    state = nodes.validate_plan(state)

    second = state["execution_plan"]["tasks"][1]
    assert second["time_requirement"]["canonical_relative"] == "tomorrow"
    assert second["time_requirement"]["requires_current_datetime"] is True
    assert "start_date" not in second["tool_input"]
    assert "end_date" not in second["tool_input"]


def test_mixed_datetime_calendar_request_completes_calendar_query_task(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("现在的日期时间是多少？顺便查一下明天的公司会议安排。", role="employee")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "get_current_datetime",
        "selected_action": "*",
        "time_requirement": {"time_reference_type": "relative", "canonical_relative": "tomorrow", "requires_current_datetime": True},
        "knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": "获取当前日期和时间",
                    "tool": "get_current_datetime",
                    "action": "*",
                    "tool_input": {"timezone": "Asia/Shanghai"},
                }
            ]
        },
    }

    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["tool"] for task in tasks] == ["get_current_datetime", "manage_company_calendar"]
    assert tasks[1]["action"] == "query"
    assert tasks[1]["tool_input"]["event_type"] == "meeting"
    assert tasks[1]["time_requirement"]["canonical_relative"] == "tomorrow"


def test_ambiguous_calendar_write_requires_clarification_before_tool_execution(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("把那个会议改成 10 点。", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "manage_company_calendar",
        "selected_action": "update",
        "time_requirement": {"time_reference_type": "ambiguous", "requires_current_datetime": False},
        "knowledge_requirement": {"should_use_rag": False},
        "missing_required_slots": ["event_id", "具体会议标题或标识"],
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
                },
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "tool_input": {"action": "update", "selector": {"event_type": "meeting"}, "time": "10:00"},
                },
            ]
        },
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "direct"
    assert state["intent"] == "need_clarification"
    assert state["selected_tool"] is None
    assert state["execution_plan"]["tasks"] == []


def test_calendar_write_intent_with_non_executable_lookup_requires_clarification(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("把那个会议改成 10 点。", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "manage_company_calendar",
        "selected_action": "update",
        "tool_input": {},
        "time_requirement": {"time_reference_type": "ambiguous", "requires_current_datetime": False},
        "knowledge_requirement": {"should_use_rag": False},
        "missing_required_slots": ["event_id"],
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": "查询当前日程中匹配会议的事件",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
                }
            ]
        },
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "direct"
    assert state["intent"] == "need_clarification"
    assert state["selected_tool"] is None
    assert state["execution_plan"]["tasks"] == []


def test_calendar_delete_with_absolute_query_date_remains_executable(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("删除 2099-01-01 的所有公司会议。", role="admin")
    state["raw_plan"] = {
        "message_type": "business_question",
        "intent": "daily_tool",
        "route": "tool",
        "standalone_query": state["question"],
        "selected_tool": "manage_company_calendar",
        "selected_action": "delete",
        "tool_input": {},
        "time_requirement": {
            "has_time_requirement": True,
            "time_reference_type": "absolute",
            "absolute_date": "2099-01-01",
            "requires_current_datetime": False,
        },
        "knowledge_requirement": {"should_use_rag": False},
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": "meeting", "date": "2099-01-01"},
                },
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "delete",
                    "tool_input": {
                        "action": "delete",
                        "selector": {"date": "2099-01-01", "event_type": "meeting"},
                    },
                },
            ]
        },
    }

    state = nodes.validate_plan(state)

    assert state["route"] == "tool"
    query_task = state["execution_plan"]["tasks"][0]
    assert query_task["tool_input"]["start_date"] == "2099-01-01"
    assert query_task["tool_input"]["end_date"] == "2099-01-01"
    assert "date" not in query_task["tool_input"]


def test_completion_reflect_does_not_treat_skipped_write_as_complete(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "ready_to_answer": True,
                    "completed_objectives": ["查询完成"],
                    "missing_objectives": ["更新未执行"],
                    "unsupported_parts": ["没有匹配日程可更新"],
                    "next_action": "answer",
                    "followup_tasks": [],
                    "reason": "写操作未完成",
                },
                ensure_ascii=False,
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("先查下周团建，再把第一个改成公司高层会议", role="admin")
    state["route"] = "tool"
    state["execution_plan"] = {
        "tasks": [
            {"task_id": "t1", "kind": "tool", "objective": "查询下周团建", "tool": "manage_company_calendar", "action": "query"},
            {"task_id": "t2", "kind": "tool", "objective": "更新第一个团建", "tool": "manage_company_calendar", "action": "update"},
        ]
    }
    state["completed_tasks"] = ["t1", "t2"]
    state["task_results"] = [
        {"task_id": "t1", "kind": "tool", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_result": {"events": []}},
        {"task_id": "t2", "kind": "tool", "status": "skipped", "tool_name": "manage_company_calendar", "action": "update", "tool_result": {"status": "skipped"}},
    ]

    state = nodes.completion_reflect(state)

    assert len(llm.calls) == 1
    assert state["completion_assessment"]["unsupported_parts"] == ["没有匹配日程可更新"]


def test_completion_reflect_can_add_missing_task_when_structure_is_ambiguous(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    followup_task = {
        "task_id": "calendar",
        "kind": "tool",
        "objective": "补查下周公司日程",
        "tool": "manage_company_calendar",
        "action": "query",
        "tool_input": {
            "action": "query",
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "event_type": "all",
            "department": "all",
            "file_path": str(path),
        },
    }
    llm = RecordingLLM(
        [
            json.dumps(
                {
                    "ready_to_answer": False,
                    "completed_objectives": ["报销制度"],
                    "missing_objectives": ["下周公司日程"],
                    "unsupported_parts": [],
                    "next_action": "replan",
                    "followup_tasks": [followup_task],
                    "reason": "缺少日程任务",
                },
                ensure_ascii=False,
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("公司下周的日程安排和公司的报销制度里对发票有什么要求？", role="admin")
    state.update(
        {
            "route": "rag",
            "execution_plan": {
                "tasks": [
                    {
                        "task_id": "policy",
                        "kind": "rag",
                        "objective": "查询公司报销制度",
                        "query": "公司的报销制度里对发票有什么要求？",
                    }
                ]
            },
            "completed_tasks": ["policy"],
            "task_results": [
                {
                    "task_id": "policy",
                    "kind": "rag",
                    "objective": "查询公司报销制度",
                    "status": "error",
                    "query": "公司的报销制度里对发票有什么要求？",
                }
            ],
        }
    )

    state = nodes.completion_reflect(state)

    assert [call["node"] for call in state["llm_calls"]] == ["completion_reflect"]
    assert state["completion_assessment"]["ready_to_answer"] is False
    assert state["current_task"]["task_id"] == "calendar"


def test_tool_success_uses_template_answer_without_answer_llm(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    tasks = [
        {
            "task_id": "calendar",
            "kind": "tool",
            "objective": "查询下周公司日程",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "next_week",
                "requires_current_datetime": True,
            },
        }
    ]
    llm = RecordingLLM(
        [
            plan_payload(tasks=tasks, route="tool", selected_tool="manage_company_calendar", selected_action="query"),
            "这是回答 LLM 综合后的下周日程说明。",
        ]
    )
    state = build_workflow(tmp_path, llm).run("公司下周的日程安排", role="employee")

    assert "产品评审会" in state["final_answer"]
    assert not any(call["node"] == "generate_answer" for call in state["llm_calls"])
    assert state["final_answer"] == state["current_tool_context"]["result_summary"]


def test_calendar_create_time_finalization_respects_action_contract(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    tasks = [
        {
            "task_id": "create",
            "kind": "tool",
            "objective": "新增下周五员工会议日程",
            "tool": "manage_company_calendar",
            "action": "create",
            "tool_input": {
                "action": "create",
                "title": "员工会议",
                "type": "meeting",
                "time": "08:00-11:00",
                "department": "all",
                "location": "会议室B",
                "file_path": str(path),
            },
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": None,
                "requires_current_datetime": True,
            },
        }
    ]
    llm = RecordingLLM(
        [
            plan_payload(tasks=tasks, route="tool", selected_tool="manage_company_calendar", selected_action="create"),
            json.dumps(
                {
                    "action": "create",
                    "title": "员工会议",
                    "type": "meeting",
                    "start_date": "2026-05-15",
                    "end_date": "2026-05-15",
                    "time": "08:00-11:00",
                    "department": "all",
                    "location": "会议室B",
                    "file_path": str(path),
                },
                ensure_ascii=False,
            ),
            "员工会议日程已创建。",
        ]
    )

    state = build_workflow(tmp_path, llm).run("帮我新增一个公司日程，时间下周五早上八点到十一点，地点会议室B，内容是员工会议。", role="admin")

    create_result = state["task_results"][0]
    assert create_result["status"] == "ok"
    assert create_result["tool_input"]["date"] == "2026-05-15"
    assert "start_date" not in create_result["tool_input"]
    assert "end_date" not in create_result["tool_input"]
    assert not any(call["node"] == "finalize_tool_input" for call in state["llm_calls"])


def test_calendar_bulk_delete_expands_query_results_to_single_event_deletes(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260512-0001",
                    "date": "2026-05-12",
                    "title": "产品评审会",
                    "type": "meeting",
                    "department": "all",
                    "time": "10:00-11:00",
                    "location": "会议室A",
                    "description": "",
                },
                {
                    "event_id": "EVT-20260513-0001",
                    "date": "2026-05-13",
                    "title": "员工培训",
                    "type": "training",
                    "department": "all",
                    "time": "14:00-16:00",
                    "location": "会议室B",
                    "description": "",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tasks = [
        {
            "task_id": "query_calendar",
            "kind": "tool",
            "objective": "查询下周所有日程以获取 event_id",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "next_week",
                "requires_current_datetime": True,
            },
        },
        {
            "task_id": "delete_calendar",
            "kind": "tool",
            "objective": "删除查询到的下周所有日程",
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "event_id": "event_id_from_query_calendar"},
            "depends_on": ["query_calendar"],
        },
    ]
    llm = RecordingLLM(
        [
            plan_payload(tasks=tasks, route="tool", selected_tool="manage_company_calendar", selected_action="query"),
            "已删除下周全部日程。",
        ]
    )

    state = build_workflow(tmp_path, llm).run("帮我删除下周的所有日程", role="admin")

    calendar_calls = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"]
    assert [call["action"] for call in calendar_calls] == ["query", "delete", "delete"]
    deleted_ids = [call["args"]["event_id"] for call in calendar_calls if call["action"] == "delete"]
    assert deleted_ids == ["EVT-20260512-0001", "EVT-20260513-0001"]
    assert all(event_id not in {"event_id_from_query_calendar", "all", "*"} for event_id in deleted_ids)
    assert not any(isinstance(event_id, list) for event_id in deleted_ids)
    assert json.loads(path.read_text(encoding="utf-8")) == []
    assert not any(result.get("status") == "error" for result in state["task_results"])


def test_calendar_bulk_delete_with_empty_query_skips_delete(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = tmp_path / "company_calendar.json"
    path.write_text("[]", encoding="utf-8")
    tasks = [
        {
            "task_id": "query_calendar",
            "kind": "tool",
            "objective": "查询下周所有日程以获取 event_id",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
            "time_requirement": {
                "has_time_requirement": True,
                "time_reference_type": "relative",
                "canonical_relative": "next_week",
                "requires_current_datetime": True,
            },
        },
        {
            "task_id": "delete_calendar",
            "kind": "tool",
            "objective": "删除查询到的下周所有日程",
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "event_id": "event_id_from_query_calendar"},
            "depends_on": ["query_calendar"],
        },
    ]
    llm = RecordingLLM(
        [
            plan_payload(tasks=tasks, route="tool", selected_tool="manage_company_calendar", selected_action="query"),
            "下周没有匹配日程可删除。",
        ]
    )

    state = build_workflow(tmp_path, llm).run("帮我删除下周的所有日程", role="admin")

    calendar_calls = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"]
    assert [call["action"] for call in calendar_calls] == ["query"]
    skipped = [result for result in state["task_results"] if result.get("task_id") == "delete_calendar"]
    assert skipped
    assert skipped[0]["status"] == "skipped"
    assert "没有匹配日程可删除" in skipped[0]["result_summary"]


def test_calendar_update_fields_are_flattened_before_tool_call(tmp_path: Path) -> None:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260516-0001",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "all",
                    "time": "16:00-18:00",
                    "location": "",
                    "description": "原始说明",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("把日程改成高层会议", role="admin")
    state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "selected_action": "update",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {
                "action": "update",
                "event_id": "EVT-20260516-0001",
                "fields": {"title": "公司高层会议", "time": "21:00-22:00", "location": "会议室A"},
                "file_path": str(path),
            },
        }
    )

    state = nodes.call_tool(state)

    args = state["tool_calls"][-1]["args"]
    assert args["title"] == "公司高层会议"
    assert args["time"] == "21:00-22:00"
    assert args["location"] == "会议室A"
    assert "fields" not in args
    event = json.loads(path.read_text(encoding="utf-8"))[0]
    assert event["title"] == "公司高层会议"
    assert event["time"] == "21:00-22:00"
    assert event["location"] == "会议室A"


def test_calendar_update_does_not_write_schema_defaults(tmp_path: Path) -> None:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260516-0001",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "Engineering",
                    "time": "16:00-18:00",
                    "location": "活动中心",
                    "description": "原始说明",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("只修改日程标题", role="admin")
    state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "selected_action": "update",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {
                "action": "update",
                "event_id": "EVT-20260516-0001",
                "title": "公司高层会议",
                "file_path": str(path),
            },
        }
    )

    state = nodes.call_tool(state)

    args = state["tool_calls"][-1]["args"]
    assert args["action"] == "update"
    assert args["event_id"] == "EVT-20260516-0001"
    assert args["title"] == "公司高层会议"
    assert args["file_path"] == str(path)
    assert not ({"type", "department", "location", "description"} & set(args))
    event = json.loads(path.read_text(encoding="utf-8"))[0]
    assert event["title"] == "公司高层会议"
    assert event["type"] == "activity"
    assert event["department"] == "Engineering"
    assert event["time"] == "16:00-18:00"
    assert event["location"] == "活动中心"
    assert event["description"] == "原始说明"


def test_calendar_update_drops_empty_optional_date_before_tool_call(tmp_path: Path) -> None:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260516-0001",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "all",
                    "time": "16:00-18:00",
                    "location": "活动中心",
                    "description": "原始说明",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("把日程改成高层会议", role="admin")
    state.update(
        {
            "route": "tool",
            "selected_tool": "manage_company_calendar",
            "selected_action": "update",
            "required_tools": ["manage_company_calendar"],
            "tool_input": {
                "action": "update",
                "event_id": "EVT-20260516-0001",
                "title": "公司高层会议",
                "date": "",
                "time": "21:00-22:00",
                "file_path": str(path),
            },
        }
    )

    state = nodes.call_tool(state)

    args = state["tool_calls"][-1]["args"]
    assert "date" not in args
    assert not state["tool_result"].get("error")
    event = json.loads(path.read_text(encoding="utf-8"))[0]
    assert event["date"] == "2026-05-16"
    assert event["title"] == "公司高层会议"


def test_calendar_update_uses_previous_context_selector_first_event(tmp_path: Path) -> None:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260516-0001",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "all",
                    "time": "16:00-18:00",
                    "location": "",
                    "description": "",
                },
                {
                    "event_id": "EVT-20260516-0002",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "all",
                    "time": "18:00-20:00",
                    "location": "",
                    "description": "",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]))
    state = create_initial_state("把星期六的第一个公司团建日程改为公司高层会议，时间晚上九点到十点，地点会议室A", role="admin")
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {"action": "query", "start_date": "2026-05-11", "end_date": "2026-05-17", "file_path": str(path)},
        "events": [
            {
                "event_id": "EVT-20260516-0001",
                "date": "2026-05-16",
                "weekday_zh": "星期六",
                "time": "16:00-18:00",
                "title": "公司团建",
                "type": "activity",
                "department": "all",
            },
            {
                "event_id": "EVT-20260516-0002",
                "date": "2026-05-16",
                "weekday_zh": "星期六",
                "time": "18:00-20:00",
                "title": "公司团建",
                "type": "activity",
                "department": "all",
            },
        ],
    }
    state["raw_plan"] = plan = json.loads(
        plan_payload(
            tasks=[
                {
                    "task_id": "update_calendar",
                    "kind": "tool",
                    "objective": "更新星期六第一个公司团建日程",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "tool_input": {
                        "action": "update",
                        "selector": {"weekday_zh": "星期六", "title": "公司团建", "ordinal": "first"},
                        "fields": {"title": "公司高层会议", "time": "21:00-22:00", "location": "会议室A"},
                        "file_path": str(path),
                    },
                }
            ],
            route="tool",
            selected_tool="manage_company_calendar",
            selected_action="update",
        )
    )
    plan["context_usage"] = "use_previous_tool_context"

    state = nodes.validate_plan(state)
    state = nodes.call_tool(state)

    args = state["tool_calls"][-1]["args"]
    assert args["event_id"] == "EVT-20260516-0001"
    assert args["title"] == "公司高层会议"
    assert args["time"] == "21:00-22:00"
    assert args["location"] == "会议室A"
    events = {event["event_id"]: event for event in json.loads(path.read_text(encoding="utf-8"))}
    assert events["EVT-20260516-0001"]["title"] == "公司高层会议"
    assert events["EVT-20260516-0001"]["time"] == "21:00-22:00"
    assert events["EVT-20260516-0001"]["location"] == "会议室A"
    assert events["EVT-20260516-0002"]["title"] == "公司团建"


def test_calendar_update_ambiguous_selector_requires_clarification(tmp_path: Path) -> None:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260516-0001",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "all",
                    "time": "16:00-18:00",
                    "location": "",
                    "description": "",
                },
                {
                    "event_id": "EVT-20260516-0002",
                    "date": "2026-05-16",
                    "title": "公司团建",
                    "type": "activity",
                    "department": "all",
                    "time": "18:00-20:00",
                    "location": "",
                    "description": "",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM(["请选择要更新的日程。"]))
    state = create_initial_state("把公司团建改成公司高层会议", role="admin")
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {"action": "query", "start_date": "2026-05-11", "end_date": "2026-05-17", "file_path": str(path)},
        "events": [
            {"event_id": "EVT-20260516-0001", "date": "2026-05-16", "weekday_zh": "星期六", "time": "16:00-18:00", "title": "公司团建", "type": "activity", "department": "all"},
            {"event_id": "EVT-20260516-0002", "date": "2026-05-16", "weekday_zh": "星期六", "time": "18:00-20:00", "title": "公司团建", "type": "activity", "department": "all"},
        ],
    }
    state["raw_plan"] = json.loads(
        plan_payload(
            tasks=[
                {
                    "task_id": "update_calendar",
                    "kind": "tool",
                    "objective": "更新公司团建日程",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "tool_input": {
                        "action": "update",
                        "selector": {"title": "公司团建"},
                        "title": "公司高层会议",
                        "file_path": str(path),
                    },
                }
            ],
            route="tool",
            selected_tool="manage_company_calendar",
            selected_action="update",
        )
    )

    state = nodes.validate_plan(state)

    assert nodes.next_after_route(state) == "generate_answer"
    assert state["tool_calls"] == []
    result = state["task_results"][0]
    assert result["status"] == "needs_clarification"
    assert result["tool_result"]["candidate_events"][0]["event_id"] == "EVT-20260516-0001"
    assert result["tool_result"]["candidate_events"][1]["event_id"] == "EVT-20260516-0002"
    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "公司团建"


def test_completion_reflect_does_not_replan_after_needs_clarification(tmp_path: Path) -> None:
    followup = json.dumps(
        {
            "ready_to_answer": False,
            "next_action": "continue",
            "followup_tasks": [
                {
                    "task_id": "unsafe_update",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "update",
                    "tool_input": {"action": "update", "event_id": "EVT-20260518-0001", "time": "10:00"},
                }
            ],
        },
        ensure_ascii=False,
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([followup]))
    state = create_initial_state("把 2026-05-18 的会议改到 10 点。", role="admin")
    state["route"] = "tool"
    state["execution_plan"] = {
        "tasks": [
            {"task_id": "t1", "kind": "tool", "tool": "manage_company_calendar", "action": "query"},
            {"task_id": "t2", "kind": "tool", "tool": "manage_company_calendar", "action": "update"},
        ]
    }
    state["completed_tasks"] = ["t1", "t2"]
    state["task_results"] = [
        {"task_id": "t1", "kind": "tool", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_result": {"events": []}},
        {
            "task_id": "t2",
            "kind": "tool",
            "status": "needs_clarification",
            "tool_name": "manage_company_calendar",
            "action": "update",
            "tool_result": {"status": "needs_clarification", "message": "匹配到多个日程，请指定 event_id。"},
        },
    ]

    state = nodes.completion_reflect(state)

    assert state["completion_assessment"]["ready_to_answer"] is True
    assert state["completion_assessment"]["next_action"] == "answer"
    assert state.get("task_queue") == []
    assert nodes.control_llm.calls == []


def test_completion_reflect_does_not_replan_after_event_not_found(tmp_path: Path) -> None:
    followup = json.dumps(
        {
            "ready_to_answer": False,
            "next_action": "replan",
            "followup_tasks": [
                {
                    "task_id": "unsafe_create",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "create",
                    "tool_input": {"action": "create", "title": "补建会议", "date": "2026-05-18", "time": "10:00-11:00"},
                }
            ],
        },
        ensure_ascii=False,
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([followup]))
    state = create_initial_state("把 EVT-20990101-9999 改到 10 点。", role="admin")
    state["route"] = "tool"
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "update_calendar",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "action": "update",
            }
        ]
    }
    state["completed_tasks"] = ["update_calendar"]
    state["task_results"] = [
        {
            "task_id": "update_calendar",
            "kind": "tool",
            "status": "error",
            "tool_name": "manage_company_calendar",
            "action": "update",
            "tool_result": {"action": "update", "error": "event not found", "event_id": "EVT-20990101-9999"},
            "result_summary": "没有找到指定 event_id 的公司日程。",
        }
    ]

    state = nodes.completion_reflect(state)

    assert state["completion_assessment"]["ready_to_answer"] is True
    assert state["completion_assessment"]["next_action"] == "answer"
    assert state.get("task_queue") == []
    assert nodes.control_llm.calls == []


def test_generate_answer_preserves_terminal_calendar_error_template(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM(["不应该调用回答模型"]))
    state = create_initial_state("把 EVT-20990101-9999 改到 10 点。", role="admin")
    state["route"] = "tool"
    state["final_answer"] = "没有找到指定 event_id 的公司日程，本次没有更新或删除。"
    state["completion_assessment"] = {"ready_to_answer": True, "next_action": "answer"}
    state["task_results"] = [
        {
            "task_id": "update_calendar",
            "kind": "tool",
            "status": "error",
            "tool_name": "manage_company_calendar",
            "action": "update",
            "tool_result": {"action": "update", "error": "event not found", "event_id": "EVT-20990101-9999"},
        }
    ]

    state = nodes.generate_answer(state)

    assert state["final_answer"] == "没有找到指定 event_id 的公司日程，本次没有更新或删除。"
    assert nodes.answer_llm.calls == []
