from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

from mini_rag.agent.context_store import SQLiteContextStore
from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.tools.daily_tools import build_default_tool_registry


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
        return FakeMessage("LLM answer fallback")


class RecordingRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, **_kwargs):
        self.queries.append(query)
        return (
            [
                Document(
                    page_content="公司标准工作时间是 9:00-18:00。",
                    metadata={"source": "hr.md", "title_path": "考勤制度", "chunk_id": "c1", "rank": 1},
                )
            ],
            {"query": query, "result_count": 1, "results": [{"source": "hr.md", "chunk_id": "c1"}]},
        )


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        AGENT_RUNTIME="langgraph",
        RERANK_ENABLED=False,
    )


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


def planner_payload(**overrides) -> str:
    payload = {
        "message_type": "business_question",
        "context_usage": "none",
        "intent": "direct",
        "route": "direct",
        "standalone_query": "test",
        "topic": "",
        "entities": [],
        "risk_level": "low",
        "selected_tool": None,
        "selected_action": None,
        "required_tools": [],
        "tool_input": {},
        "needs_time_resolution": False,
        "relative_time": None,
        "missing_required_slots": [],
        "reason": "test",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def calendar_path(tmp_path: Path) -> Path:
    path = tmp_path / "company_calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260506-0001",
                    "date": "2026-05-06",
                    "title": "全员周会",
                    "type": "meeting",
                    "department": "all",
                    "time": "10:00-11:00",
                    "location": "线上会议",
                    "description": "每周同步",
                },
                {
                    "event_id": "EVT-20260512-0001",
                    "date": "2026-05-12",
                    "title": "团队团建",
                    "type": "activity",
                    "department": "all",
                    "time": "18:00-20:00",
                    "location": "活动中心",
                    "description": "团队活动",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def parse_contracts(text: str) -> list[dict]:
    return json.loads(text)


def test_permission_aware_contracts_are_filtered_by_role() -> None:
    registry = build_default_tool_registry()

    public_contracts = parse_contracts(registry.format_tool_contracts_for_prompt(role="public"))
    employee_contracts = parse_contracts(registry.format_tool_contracts_for_prompt(role="employee"))
    admin_contracts = parse_contracts(registry.format_tool_contracts_for_prompt(role="admin"))

    public_names = {item["name"] for item in public_contracts}
    assert public_names == {"search_knowledge_base", "get_current_datetime"}

    employee_calendar = next(item for item in employee_contracts if item["name"] == "manage_company_calendar")
    assert set(employee_calendar["actions"]) == {"query"}
    assert "query_attendance_summary" in {item["name"] for item in employee_contracts}

    admin_calendar = next(item for item in admin_contracts if item["name"] == "manage_company_calendar")
    assert set(admin_calendar["actions"]) == {"query", "create", "update", "delete"}


def test_public_calendar_question_is_permission_required_without_tool_name(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            planner_payload(
                intent="permission_required",
                route="direct",
                standalone_query="公司这周有什么日程安排",
                topic="calendar",
                reason="角色无日程权限",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("公司这周有什么日程安排", role="public")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.generate_answer(state)

    prompt = llm.calls[0][-1][1]
    assert "manage_company_calendar" not in prompt
    assert state["route"] == "direct"
    assert state["intent"] == "permission_required"
    assert state["selected_tool"] is None
    assert "manage_company_calendar" not in state["final_answer"]
    assert "无法查看公司内部日程" in state["final_answer"]
    assert len(llm.calls) == 1


def test_smalltalk_does_not_use_previous_tool_context_or_tools(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = SQLiteContextStore(settings.context_db_path)
    store.append_turn(
        "s1",
        "昨天公司的出勤情况如何？",
        "查询昨天公司出勤",
        "考勤汇总",
        [],
        {
            "current_tool_context": {
                "domain": "attendance",
                "tool_name": "query_attendance_summary",
                "tool_input": {"start_date": "2026-05-07", "end_date": "2026-05-07"},
                "result_summary": "昨天出勤汇总",
            }
        },
    )
    llm = RecordingLLM(
        [
            planner_payload(
                message_type="smalltalk",
                context_usage="none",
                intent="smalltalk",
                route="direct",
                standalone_query="你好",
                reason="寒暄",
            )
        ]
    )
    nodes = AgenticRAGNodes(settings, llm=llm)
    nodes.context_store = store
    state = create_initial_state("你好", session_id="s1", role="employee")

    state = nodes.load_context(state)
    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.generate_answer(state)

    assert state["message_type"] == "smalltalk"
    assert state["context_usage"] == "none"
    assert state["route"] == "direct"
    assert state["selected_tool"] is None
    assert state["tool_calls"] == []
    assert state["retrieved_docs"] == []
    assert "企业知识库助手" in state["final_answer"]
    assert len(llm.calls) == 1


def test_employee_calendar_query_uses_query_action_and_datetime(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    llm = RecordingLLM(
        [
            planner_payload(
                intent="daily_tool",
                route="tool",
                standalone_query="查询公司这周日程安排",
                topic="calendar",
                selected_tool="manage_company_calendar",
                selected_action="query",
                required_tools=["manage_company_calendar"],
                tool_input={"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
                needs_time_resolution=True,
                relative_time="this_week",
                reason="查询日程",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("公司这周有什么日程安排", role="employee")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.call_tool(state)

    assert state["selected_action"] == "query"
    names = [call["tool_name"] for call in state["tool_calls"]]
    assert "get_current_datetime" in names
    calendar_call = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]
    assert calendar_call["args"]["action"] == "query"
    assert calendar_call["args"]["start_date"] == "2026-05-04"
    assert calendar_call["args"]["end_date"] == "2026-05-10"


def test_allowed_selected_tool_normalizes_conflicting_direct_route(tmp_path: Path) -> None:
    path = calendar_path(tmp_path)
    llm = RecordingLLM(
        [
            planner_payload(
                message_type="followup_question",
                context_usage="use_previous_tool_context",
                intent="direct",
                route="direct",
                standalone_query="下周有什么日程安排？",
                topic="公司日程",
                selected_tool="manage_company_calendar",
                selected_action="query",
                required_tools=[],
                tool_input={
                    "action": "query",
                    "start_date": "2026-05-11",
                    "end_date": "2026-05-17",
                    "event_type": "all",
                    "department": "all",
                    "file_path": str(path),
                },
                reason="延续上轮日程查询",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("下周呢？", role="admin")

    state = nodes.understand_query(state)
    state = nodes.route(state)

    assert state["route"] == "tool"
    assert nodes.next_after_route(state) == "call_tool"

    state = nodes.call_tool(state)

    calendar_call = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]
    assert calendar_call["args"]["start_date"] == "2026-05-11"
    assert calendar_call["args"]["end_date"] == "2026-05-17"
    assert state["tool_result"]["events"][0]["title"] == "团队团建"


def test_current_relative_time_overrides_context_derived_planner_dates(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    llm = RecordingLLM(
        [
            planner_payload(
                message_type="business_question",
                context_usage="use_previous_tool_context",
                intent="daily_tool",
                route="tool",
                standalone_query="下周的公司日程",
                topic="公司日程",
                selected_tool="manage_company_calendar",
                selected_action="query",
                required_tools=["manage_company_calendar"],
                tool_input={
                    "action": "query",
                    "start_date": "2026-05-25",
                    "end_date": "2026-06-01",
                    "event_type": "all",
                    "department": "all",
                    "file_path": str(path),
                },
                needs_time_resolution=False,
                relative_time=None,
                reason="使用历史上下文查询下周日程",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("下周的公司日程", role="admin")
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {
            "action": "query",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "event_type": "all",
            "department": "all",
        },
    }

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.call_tool(state)

    names = [call["tool_name"] for call in state["tool_calls"]]
    assert "get_current_datetime" in names
    calendar_call = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]
    assert calendar_call["args"]["start_date"] == "2026-05-11"
    assert calendar_call["args"]["end_date"] == "2026-05-17"
    assert state["relative_time"] == "next_week"
    assert state["tool_result"]["events"][0]["title"] == "团队团建"


def test_direct_datetime_question_is_normalized_to_datetime_tool(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    llm = RecordingLLM(
        [
            planner_payload(
                message_type="business_question",
                context_usage="none",
                intent="direct",
                route="direct",
                standalone_query="今天星期几？",
                topic="日期时间",
                selected_tool=None,
                selected_action=None,
                tool_input={},
                needs_time_resolution=False,
                relative_time=None,
                reason="日期问题",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("今天星期几？", role="employee")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.call_tool(state)

    assert state["route"] == "tool"
    assert state["selected_tool"] == "get_current_datetime"
    assert state["relative_time"] == "today"
    assert state["tool_calls"][-1]["tool_name"] == "get_current_datetime"
    assert "当前日期" in state["final_answer"]


def test_smalltalk_discards_accidental_selected_tool(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            planner_payload(
                message_type="smalltalk",
                context_usage="none",
                intent="smalltalk",
                route="direct",
                standalone_query="你好",
                topic="",
                selected_tool="manage_company_calendar",
                selected_action="query",
                tool_input={"action": "query"},
                reason="寒暄",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("你好", role="admin")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.generate_answer(state)

    assert state["route"] == "direct"
    assert state["intent"] == "smalltalk"
    assert state["selected_tool"] is None
    assert state["selected_action"] is None
    assert state["tool_input"] == {}
    assert state["tool_calls"] == []
    assert "企业知识库助手" in state["final_answer"]


def test_employee_create_calendar_is_permission_required_direct(tmp_path: Path) -> None:
    registry = build_default_tool_registry()
    employee_contracts = parse_contracts(registry.format_tool_contracts_for_prompt(role="employee"))
    employee_calendar = next(item for item in employee_contracts if item["name"] == "manage_company_calendar")
    assert set(employee_calendar["actions"]) == {"query"}

    llm = RecordingLLM(
        [
            planner_payload(
                intent="permission_required",
                route="direct",
                standalone_query="添加明天下午三点的全员会",
                topic="calendar_write",
                reason="无写权限",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("帮我添加明天下午三点的全员会", role="employee")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.generate_answer(state)

    assert state["route"] == "direct"
    assert state["intent"] == "permission_required"
    assert state["selected_tool"] is None
    assert "只有 admin 可以新增、更新或删除日程" in state["final_answer"]


def test_admin_create_calendar_action_writes_json(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    path = calendar_path(tmp_path)
    llm = RecordingLLM(
        [
            planner_payload(
                intent="daily_tool",
                route="tool",
                standalone_query="创建明天下午三点的全员会",
                topic="calendar",
                selected_tool="manage_company_calendar",
                selected_action="create",
                required_tools=["manage_company_calendar"],
                tool_input={
                    "action": "create",
                    "title": "全员会",
                    "type": "meeting",
                    "time": "15:00",
                    "department": "all",
                    "file_path": str(path),
                },
                needs_time_resolution=True,
                relative_time="tomorrow",
                reason="创建日程",
            )
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("帮我添加明天下午三点的全员会", role="admin")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.call_tool(state)

    assert state["selected_action"] == "create"
    assert state["tool_result"]["status"] == "created"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert any(event["title"] == "全员会" and event["date"] == "2026-05-10" for event in saved)


def test_calendar_event_type_contract_keeps_generic_activity_as_all(tmp_path: Path, monkeypatch) -> None:
    import mini_rag.graph.nodes as nodes_module

    monkeypatch.setattr(nodes_module, "get_current_datetime", fake_datetime)
    contracts = build_default_tool_registry().format_tool_contracts_for_prompt(role="employee")
    assert "公司有什么活动" in contracts
    assert "event_type=all" in contracts

    path = calendar_path(tmp_path)
    nodes = AgenticRAGNodes(
        make_settings(tmp_path),
        llm=RecordingLLM(
            [
                planner_payload(
                    intent="daily_tool",
                    route="tool",
                    standalone_query="查询下周公司活动安排",
                    topic="calendar",
                    selected_tool="manage_company_calendar",
                    selected_action="query",
                    required_tools=["manage_company_calendar"],
                    tool_input={"action": "query", "event_type": "all", "department": "all", "file_path": str(path)},
                    needs_time_resolution=True,
                    relative_time="next_week",
                )
            ]
        ),
    )
    state = create_initial_state("下周公司有什么活动", role="employee")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.call_tool(state)

    calendar_call = [call for call in state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]
    assert calendar_call["args"]["event_type"] == "all"

    nodes = AgenticRAGNodes(
        make_settings(tmp_path / "team"),
        llm=RecordingLLM(
            [
                planner_payload(
                    intent="daily_tool",
                    route="tool",
                    standalone_query="查询下周团建安排",
                    topic="calendar",
                    selected_tool="manage_company_calendar",
                    selected_action="query",
                    required_tools=["manage_company_calendar"],
                    tool_input={"action": "query", "event_type": "activity", "department": "all", "file_path": str(path)},
                    needs_time_resolution=True,
                    relative_time="next_week",
                )
            ]
        ),
    )
    team_state = create_initial_state("下周有什么团建", role="employee")
    team_state = nodes.understand_query(team_state)
    team_state = nodes.route(team_state)
    team_state = nodes.call_tool(team_state)
    team_calendar_call = [call for call in team_state["tool_calls"] if call["tool_name"] == "manage_company_calendar"][-1]
    assert team_calendar_call["args"]["event_type"] == "activity"


def test_rag_route_still_retrieves_knowledge_base(tmp_path: Path) -> None:
    llm = RecordingLLM(
        [
            planner_payload(
                message_type="business_question",
                context_usage="none",
                intent="rag_fact",
                route="rag",
                standalone_query="公司的标准工作时间是什么？",
                topic="attendance_policy",
                reason="制度问题",
            ),
            json.dumps(
                {
                    "search_tasks": [
                        {"query": "公司的标准工作时间是什么？", "purpose": "answer_question", "target_entity": None}
                    ],
                    "reason": "单问题检索",
                },
                ensure_ascii=False,
            ),
            "公司的标准工作时间是 9:00-18:00。\n\n引用：hr.md / 考勤制度 / c1",
        ]
    )
    retriever = RecordingRetriever()
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=retriever)
    state = create_initial_state("公司的标准工作时间是什么？", role="employee")

    state = nodes.check_permission(state)
    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.plan_retrieval(state)
    state = nodes.retrieve(state)
    state = nodes.generate_answer(state)

    assert state["route"] == "rag"
    assert retriever.queries == ["公司的标准工作时间是什么？"]
    assert state["sources"]
    assert "标准工作时间" in state["final_answer"]
