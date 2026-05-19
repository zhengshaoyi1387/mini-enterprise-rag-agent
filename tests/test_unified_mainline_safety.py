from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state


class NoopLLM:
    def invoke(self, _messages):
        class Message:
            content = '{"next_action":"finish","finish_reason":"done"}'

        return Message()


class QueueLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)

    def invoke(self, _messages):
        class Message:
            def __init__(self, content: str):
                self.content = content

        if self.contents:
            return Message(self.contents.pop(0))
        return Message('{"next_action":"finish","finish_reason":"done"}')


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def _prepare_state(nodes: AgenticRAGNodes, state: dict, tasks: list[dict]):
    state = nodes.build_runtime_context(state)
    state["raw_plan"] = {
        "overall_intent": "calendar",
        "requires_tools": True,
        "tasks": tasks,
        "answer_style": "concise",
    }
    state["planner_schema_version"] = "runtime_v2"
    state["execution_plan"] = {"tasks": tasks, "strategy": "concise"}
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    return state


def test_employee_calendar_create_is_blocked_before_tool_execution(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("创建后天 15:00-16:00 的项目复盘会", role="employee", override_now="2026-05-18T09:30:00+08:00")

    state = _prepare_state(
        nodes,
        state,
        [
            {
                "task_id": "create",
                "kind": "tool",
                "objective": "创建项目复盘会",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "create",
                "time_expression": "后天",
                "tool_input": {"action": "create", "title": "项目复盘会", "time": "15:00-16:00", "location": "会议室A"},
            }
        ],
    )

    assert state["route"] == "direct"
    assert state["intent"] == "permission_required"
    assert state["tool_calls"] == []


def test_admin_calendar_create_consumes_resolved_time_only(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("创建后天 15:00-16:00 的项目复盘会", role="admin", override_now="2026-05-18T09:30:00+08:00")

    state = _prepare_state(
        nodes,
        state,
        [
            {
                "task_id": "create",
                "kind": "tool",
                "objective": "创建项目复盘会",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "create",
                "time_expression": "后天",
                "tool_input": {"action": "create", "title": "项目复盘会", "time": "15:00-16:00", "location": "会议室A"},
            }
        ],
    )

    task = state["execution_plan"]["tasks"][0]
    assert state["plan_validation"]["validation_status"] == "valid"
    assert task["tool_input"]["date"] == "2026-05-20"
    assert task["resolved_time"]["items"][0]["weekday_zh"] == "星期三"


def test_validate_plan_keeps_executable_tasks_when_later_create_needs_clarification(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("先查明天会议，再创建一个还没说明日期的会议", role="admin", override_now="2026-05-18T09:30:00+08:00")

    state = _prepare_state(
        nodes,
        state,
        [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询明天会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "明天",
                "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
            },
            {
                "task_id": "create",
                "kind": "tool",
                "objective": "创建会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "create",
                "tool_input": {"action": "create", "title": "待定会议", "time": "10:00-11:00", "location": "会议室A"},
            },
        ],
    )

    assert state["plan_validation"]["validation_status"] == "partial"
    assert [task["task_id"] for task in state["plan_validation"]["executable_tasks"]] == ["query"]
    assert [task["task_id"] for task in state["plan_validation"]["clarification_tasks"]] == ["create"]
    assert [task["task_id"] for task in state["execution_plan"]["tasks"]] == ["query"]
    assert state["execution_plan"]["tasks"][0]["tool_input"]["start_date"] == "2026-05-19"


def test_attendance_abnormal_query_uses_resolved_week_range(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("查本周考勤异常", role="hr", override_now="2026-05-18T09:30:00+08:00")

    state = _prepare_state(
        nodes,
        state,
        [
            {
                "task_id": "attendance",
                "kind": "tool",
                "objective": "查询本周考勤异常",
                "tool": "query_attendance_summary",
                "tool_name": "query_attendance_summary",
                "action": "query",
                "time_expression": "本周",
                "tool_input": {"status_filters": ["late", "leave", "absent"], "include_records": True, "group_by": "employee"},
            }
        ],
    )

    task = state["execution_plan"]["tasks"][0]
    assert state["plan_validation"]["validation_status"] == "valid"
    assert task["tool_input"]["start_date"] == "2026-05-18"
    assert task["tool_input"]["end_date"] == "2026-05-24"
    assert task["tool_input"]["status_filters"] == ["late", "leave", "absent"]


def test_complex_calendar_write_keeps_valid_tasks_and_resolves_previous_context_selectors(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"next_action":"call_tool","task_id":"t2","tool_name":"manage_company_calendar"}',
            '{"next_action":"call_tool","task_id":"t3","tool_name":"manage_company_calendar"}',
            '{"next_action":"call_tool","task_id":"t4","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state(
        "删除第一个会议，然后把第二个会议的地点改为会议室B，然后创建一个会议：时间星期一晚上九点到十点，员工会议，地点会议室D",
        role="admin",
        override_now="2026-05-18T23:47:00+08:00",
    )
    state = nodes.build_runtime_context(state)
    state["previous_tool_context"] = {
        "tool_name": "manage_company_calendar",
        "tool_input": {"start_date": "2026-05-18", "end_date": "2026-05-18"},
        "events": [
            {"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "location": "会议室B"},
            {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "location": "会议室C"},
        ],
    }
    tasks = [
        {
            "task_id": "t2",
            "kind": "tool",
            "objective": "删除第一个会议",
            "tool": "manage_company_calendar",
            "tool_name": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "selector": {"ordinal": "first"}},
        },
        {
            "task_id": "t3",
            "kind": "tool",
            "objective": "把第二个会议的地点改为会议室B",
            "tool": "manage_company_calendar",
            "tool_name": "manage_company_calendar",
            "action": "update",
            "tool_input": {"action": "update", "selector": {"ordinal": "2"}, "location": "会议室B"},
        },
        {
            "task_id": "t4",
            "kind": "tool",
            "objective": "创建员工会议",
            "tool": "manage_company_calendar",
            "tool_name": "manage_company_calendar",
            "action": "create",
            "time_expression": "星期一晚上九点到十点",
            "tool_input": {"action": "create", "title": "员工会议", "time": "21:00-22:00", "location": "会议室D"},
        },
    ]
    state["execution_plan"] = {"tasks": tasks, "strategy": "concise"}

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    assert state["plan_validation"]["validation_status"] in {"valid", "partial"}
    assert [task["task_id"] for task in state["execution_plan"]["tasks"]] == ["t2", "t3", "t4"]
    assert state["execution_plan"]["tasks"][2]["tool_input"]["date"] == "2026-05-25"

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        action = str(payload.get("action") or "")
        result = {"action": action, "status": "ok", "message": "ok"}
        if action in {"create", "update"}:
            result["event"] = {
                "event_id": payload.get("event_id") or "EVT-20260525-0001",
                "date": payload.get("date") or "2026-05-18",
                "time": payload.get("time") or "21:00-22:00",
                "title": payload.get("title") or "研发部周会",
                "location": payload.get("location") or "会议室B",
            }
        call_state["tool_result"] = result
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes.call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["event_id"] == "EVT-20260518-0001"
    assert recorded_inputs[1]["event_id"] == "EVT-20260518-0002"
    assert recorded_inputs[2]["date"] == "2026-05-25"
    assert recorded_inputs[2]["time"] == "21:00-22:00"
    assert recorded_inputs[2]["title"] == "员工会议"
    assert recorded_inputs[2]["location"] == "会议室D"
    assert state["react_status"] == "success"
    assert state["react_steps"]
    assert state["completion_assessment"]["ready_to_answer"] is True


def test_react_need_clarification_is_not_ready_to_answer(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=QueueLLM(['{"next_action":"ask_clarification","task_id":"t1","clarification":"请指定会议。"}']))
    state = create_initial_state("把会议改到会议室B", role="admin", override_now="2026-05-18T09:30:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "t1",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "selector": {"title_contains": "会议"}, "location": "会议室B"},
            }
        ]
    }

    state = nodes.react_execute(state)

    assert state["react_status"] == "need_clarification"
    assert state["completion_assessment"]["ready_to_answer"] is False
