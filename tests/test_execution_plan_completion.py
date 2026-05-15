from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

from mini_rag.config import Settings
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
        AGENT_RUNTIME="langgraph",
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


def test_compound_calendar_create_then_query_executes_both_and_llm_answers(tmp_path: Path, monkeypatch) -> None:
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
            ready_reflection(),
            "已新增员工培训，并查询到下周公司日程包含产品评审会和员工培训。",
        ]
    )
    state = build_workflow(tmp_path, llm).run("帮我新增一个公司日程，时间下周三早上九点到十一点，地点会议室B，内容是员工培训。然后告诉我公司下周的日程安排。", role="admin")

    calendar_calls = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"]
    assert [call["action"] for call in calendar_calls] == ["create", "query"]
    assert [result["task_id"] for result in state["task_results"]] == ["t1", "t2"]
    assert "新增员工培训" in state["final_answer"]
    assert any(call["node"] == "completion_reflect" for call in state["llm_calls"])
    assert any(call["node"] == "generate_answer" for call in state["llm_calls"])


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
            json.dumps({"search_tasks": [{"query": "公司的报销制度里对发票有什么要求？", "purpose": "answer", "target_entity": None}], "reason": "查制度"}, ensure_ascii=False),
            ready_reflection(),
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


def test_completion_reflect_can_add_missing_task_before_answer(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    initial_tasks = [
        {
            "task_id": "policy",
            "kind": "rag",
            "objective": "查询公司报销制度",
            "query": "公司的报销制度里对发票有什么要求？",
        }
    ]
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
            plan_payload(tasks=initial_tasks, route="rag"),
            json.dumps({"search_tasks": [{"query": "公司的报销制度里对发票有什么要求？", "purpose": "answer", "target_entity": None}], "reason": "查制度"}, ensure_ascii=False),
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
            ),
            ready_reflection(),
            "已补全：下周公司有产品评审会；发票要求真实有效。",
        ]
    )
    retriever = RecordingRetriever()
    state = build_workflow(tmp_path, llm, retriever=retriever).run("公司下周的日程安排和公司的报销制度里对发票有什么要求？", role="admin")

    assert [result["task_id"] for result in state["task_results"]] == ["policy", "calendar"]
    assert len([call for call in state["llm_calls"] if call["node"] == "completion_reflect"]) == 2
    assert "已补全" in state["final_answer"]


def test_tool_success_does_not_skip_answer_llm(tmp_path: Path, monkeypatch) -> None:
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
            ready_reflection(),
            "这是回答 LLM 综合后的下周日程说明。",
        ]
    )
    state = build_workflow(tmp_path, llm).run("公司下周的日程安排", role="employee")

    assert state["final_answer"] == "这是回答 LLM 综合后的下周日程说明。"
    assert any(call["node"] == "generate_answer" for call in state["llm_calls"])
    assert state["final_answer"] != state["current_tool_context"]["result_summary"]


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
            ready_reflection(),
            "员工会议日程已创建。",
        ]
    )

    state = build_workflow(tmp_path, llm).run("帮我新增一个公司日程，时间下周五早上八点到十一点，地点会议室B，内容是员工会议。", role="admin")

    create_result = state["task_results"][0]
    assert create_result["status"] == "ok"
    assert create_result["tool_input"]["date"] == "2026-05-15"
    assert "start_date" not in create_result["tool_input"]
    assert "end_date" not in create_result["tool_input"]
