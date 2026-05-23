from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.answer.packet import build_answer_packet
from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state


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
        ENTERPRISE_DB_PATH=tmp_path / "enterprise_demo.db",
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


def test_calendar_tool_payload_uses_runtime_enterprise_db_path(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    nodes = AgenticRAGNodes(settings, llm=NoopLLM())
    state = create_initial_state("查询下周日公司会议", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["selected_action"] = "query"
    state["tool_input"] = {
        "action": "query",
        "start_date": "2026-05-31",
        "end_date": "2026-05-31",
        "event_type": "meeting",
    }

    payload = nodes._build_tool_payload(state, "manage_company_calendar", "admin")

    assert payload["db_path"] == str(settings.enterprise_db_path)


def test_attendance_tool_payload_uses_runtime_enterprise_db_path(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    nodes = AgenticRAGNodes(settings, llm=NoopLLM())
    state = create_initial_state("查一下上周考勤异常", role="hr", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["tool_input"] = {
        "start_date": "2026-05-11",
        "end_date": "2026-05-17",
        "status_filters": ["late", "leave", "absent"],
        "include_records": True,
    }

    payload = nodes._build_tool_payload(state, "query_attendance_summary", "hr")

    assert payload["db_path"] == str(settings.enterprise_db_path)


def test_calendar_query_then_update_executes_against_runtime_enterprise_db(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    initialize_enterprise_demo_db(settings.enterprise_db_path, reset=True)
    nodes = AgenticRAGNodes(settings, llm=NoopLLM())
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = _prepare_state(
        nodes,
        state,
        [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询下周日公司会议",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_input": {"action": "query", "event_type": "meeting", "date_expression": "下周日"},
                "depends_on": [],
            },
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "更新查询到的会议地点",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "event_id": "<queried_event_id>", "location": "1号会议室"},
                "depends_on": ["query"],
            },
        ],
    )

    state = nodes.react_execute(state)

    calendar_calls = [call for call in state["tool_calls"] if call.get("tool_name") == "manage_company_calendar"]
    assert [call.get("action") for call in calendar_calls] == ["query", "update"]
    assert all(call["args"]["db_path"] == str(settings.enterprise_db_path) for call in calendar_calls)
    assert state["task_results"][-1]["tool_result"]["status"] == "updated"
    assert state["task_results"][-1]["tool_result"]["event"]["location"] == "1号会议室"


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


def test_planner_stage_strips_computed_calendar_dates(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"query","kind":"tool","objective":"查询下周日公司会议",'
            '"tool_name":"manage_company_calendar","action":"query","time_expression":"下周日",'
            '"tool_input":{"action":"query","event_type":"meeting","start_date":"2026-05-25","end_date":"2026-05-25"}},'
            '{"task_id":"update","kind":"tool","objective":"改到晚上九点到九点半",'
            '"tool_name":"manage_company_calendar","action":"update","time_expression":"晚上九点到九点半",'
            '"tool_input":{"action":"update","event_id":null,"date":"2026-05-25","time":"21:00-21:30"},'
            '"depends_on":["query"]}],"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议改到晚上九点到九点半。", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)

    query_input = state["execution_plan"]["tasks"][0]["tool_input"]
    update_input = state["execution_plan"]["tasks"][1]["tool_input"]
    assert "start_date" not in query_input
    assert "end_date" not in query_input
    assert "date" not in update_input
    assert update_input["time"] == "21:00-21:30"


def test_planner_stage_drops_computed_time_expression_not_in_user_text(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"query","kind":"tool","objective":"查询下周日公司会议",'
            '"tool_name":"manage_company_calendar","action":"query","time_expression":"2026-05-31",'
            '"tool_input":{"action":"query","event_type":"meeting"}},'
            '{"task_id":"update","kind":"tool","objective":"改到下个星期日",'
            '"tool_name":"manage_company_calendar","action":"update","tool_input":{"action":"update",'
            '"pending_update":{"date_expression":"2026-06-07"}},"depends_on":["query"]}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议改到下个星期日。", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)

    query_task, update_task = state["execution_plan"]["tasks"]
    assert query_task.get("time_expression", "") == ""
    assert "pending_update" not in update_task["tool_input"]
    assert update_task.get("time_expression", "") == ""


def test_query_first_update_does_not_trust_planner_residual_date(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(
        make_settings(tmp_path),
        llm=QueueLLM(
            [
                '{"next_action":"call_tool","task_id":"update","tool_name":"manage_company_calendar",'
                '"tool_input":{"action":"update","date":"2026-05-25","time":"21:00-21:30"}}'
            ]
        ),
    )
    state = create_initial_state("把下周日的公司会议改到晚上九点到九点半。", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询下周日公司会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "下周日",
                "tool_input": {"action": "query", "event_type": "meeting", "start_date": "2026-05-25", "end_date": "2026-05-25"},
            },
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "改到晚上九点到九点半",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "time_expression": "晚上九点到九点半",
                "tool_input": {"action": "update", "event_id": None, "date": "2026-05-25", "time": "21:00-21:30"},
                "depends_on": ["query"],
            },
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert tasks[0]["tool_input"]["start_date"] == "2026-05-31"
    assert tasks[0]["tool_input"]["end_date"] == "2026-05-31"
    assert "date" not in tasks[1]["tool_input"]

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        action = str(payload.get("action") or "")
        if action == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "16:00-17:00",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": payload.get("time"),
                    "title": "OKR 季度复盘",
                    "location": "线上会议",
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert recorded_inputs[1]["event_id"] == "EVT-20260531-0001"
    assert recorded_inputs[1]["time"] == "21:00-21:30"
    assert "date" not in recorded_inputs[1]
    assert state["react_status"] == "success"


def test_followup_update_inherits_event_id_from_previous_tool_input(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=QueueLLM(['{"next_action":"call_tool","task_id":"update","tool_name":"manage_company_calendar"}']))
    state = create_initial_state("改到下个星期日", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {
            "action": "update",
            "event_id": "EVT-20260531-0001",
            "title": "OKR 季度复盘",
            "date": "2026-05-24",
            "location": "线上会议",
        },
    }
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "更新会议到下一个星期日",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "time_expression": "下个星期日",
                "tool_input": {"action": "update"},
            }
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    task = state["execution_plan"]["tasks"][0]
    assert state["plan_validation"]["validation_status"] == "valid"
    assert task["tool_input"] == {
        "action": "update",
        "date": "2026-05-31",
        "event_id": "EVT-20260531-0001",
        "_inherited_event_id_from_previous_context": True,
    }
    assert task["resolved_time"]["items"][0]["weekday_zh"] == "星期日"

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append({key: value for key, value in payload.items() if not str(key).startswith("_")})
        call_state["tool_result"] = {
            "action": "update",
            "status": "updated",
            "event": {
                "event_id": payload.get("event_id"),
                "date": payload.get("date"),
                "weekday_zh": "星期日",
                "time": "09:00-09:30",
                "title": "OKR 季度复盘",
                "location": "线上会议",
            },
        }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs == [{"action": "update", "date": "2026-05-31", "event_id": "EVT-20260531-0001"}]
    assert state["react_status"] == "success"


def test_followup_update_with_multiple_previous_events_needs_clarification(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("改到下个星期日", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "events": [
            {"event_id": "EVT-20260531-0001", "date": "2026-05-24", "title": "OKR 季度复盘"},
            {"event_id": "EVT-20260531-0002", "date": "2026-05-24", "title": "研发例会"},
        ],
    }
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "更新会议到下一个星期日",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "time_expression": "下个星期日",
                "tool_input": {"action": "update"},
            }
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    assert state["plan_validation"]["validation_status"] == "needs_clarification"
    assert state["execution_plan"]["tasks"] == []
    assert state["tool_calls"] == []


def test_explicit_new_calendar_target_uses_query_not_previous_event_id(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(
        make_settings(tmp_path),
        llm=QueueLLM(
            [
                '{"next_action":"call_tool","task_id":"update","tool_name":"manage_company_calendar",'
                '"tool_input":{"action":"update","event_id":"EVT-OLD-CANNOT-BE-USED","date":"2026-05-30"}}'
            ]
        ),
    )
    state = create_initial_state("把下周日的公司会议改到下个星期日", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {"action": "update", "event_id": "EVT-20260524-0009", "date": "2026-05-24"},
    }
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询下周日公司会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "下周日",
                "tool_input": {"action": "query", "event_type": "meeting"},
            },
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "把查询到的公司会议改到下个星期日",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "time_expression": "下个星期日",
                "tool_input": {"action": "update"},
                "depends_on": ["query"],
            },
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    query_task, update_task = state["execution_plan"]["tasks"]
    assert query_task["tool_input"]["start_date"] == "2026-05-31"
    assert update_task["tool_input"]["date"] == "2026-05-31"
    assert "event_id" not in update_task["tool_input"]

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "events": [
                    {
                        "event_id": "EVT-20260531-NEW1",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "09:00-09:30",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": payload.get("date"),
                    "weekday_zh": "星期日",
                    "title": "OKR 季度复盘",
                    "location": "线上会议",
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert recorded_inputs[1]["event_id"] == "EVT-20260531-NEW1"
    assert recorded_inputs[1]["date"] == "2026-05-31"
    assert state["react_status"] == "success"


def test_query_then_update_location_expands_to_query_and_update(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"calendar_write","kind":"tool","objective":"查询下周日公司会议并更新地点",'
            '"tool_name":"manage_company_calendar","action":"query_then_update","time_expression":"下周日",'
            '"tool_input":{"target":{"event_type":"meeting","department":"all"},'
            '"pending_update":{"location":"3号会议室"}}}],'
            '"answer_style":null}',
            '{"next_action":"call_tool","task_id":"calendar_write_update","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成 3 号会议室。", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    planned_tasks = state["execution_plan"]["tasks"]
    assert [task["action"] for task in planned_tasks] == ["query", "update"]
    assert planned_tasks[1]["tool_input"]["pending_update"] == {"location": "3号会议室"}

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["action"] for task in tasks] == ["query", "update"]
    assert tasks[1]["tool_input"]["pending_update"] == {"location": "3号会议室"}
    assert "event_id" not in tasks[1]["tool_input"]

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "09:00-09:30",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "title": "OKR 季度复盘",
                    "location": payload.get("location"),
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert recorded_inputs[1]["event_id"] == "EVT-20260531-0001"
    assert recorded_inputs[1] == {"action": "update", "location": "3号会议室", "event_id": "EVT-20260531-0001"}
    assert state["react_status"] == "success"


def test_calendar_query_tool_input_date_expression_is_resolved_and_removed(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询下周日公司会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_input": {"action": "query", "event_type": "meeting", "date_expression": "下周日"},
            }
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)

    task = state["execution_plan"]["tasks"][0]
    assert task["time_expression"] == "下周日"
    assert task["tool_input"]["start_date"] == "2026-05-31"
    assert task["tool_input"]["end_date"] == "2026-05-31"
    assert "date_expression" not in task["tool_input"]
    assert state["resolved_time_facts"][0]["time_expression"] == "下周日"


def test_query_dep_update_placeholder_event_id_survives_validation(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=NoopLLM())
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询下周日公司会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_input": {"action": "query", "event_type": "meeting", "date_expression": "下周日"},
            },
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "更新查询到的公司会议地点",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "event_id": "<queried_event_id>", "location": "1号会议室"},
                "depends_on": ["query"],
            },
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    assert state["plan_validation"]["validation_status"] == "valid"
    assert [task["task_id"] for task in state["plan_validation"]["executable_tasks"]] == ["query", "update"]
    query_task, update_task = state["execution_plan"]["tasks"]
    assert query_task["tool_input"]["start_date"] == "2026-05-31"
    assert "date_expression" not in query_task["tool_input"]
    assert update_task["tool_input"]["event_id"] == "<queried_event_id>"
    assert state["plan_validation"]["clarification_tasks"] == []


def test_query_dep_update_placeholder_event_id_executes_after_unique_query_result(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(
        make_settings(tmp_path),
        llm=QueueLLM(['{"next_action":"call_tool","task_id":"update","tool_name":"manage_company_calendar"}']),
    )
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "query",
                "kind": "tool",
                "objective": "查询下周日公司会议",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_input": {"action": "query", "event_type": "meeting", "date_expression": "下周日"},
            },
            {
                "task_id": "update",
                "kind": "tool",
                "objective": "更新查询到的公司会议地点",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "event_id": "<queried_event_id>", "location": "1号会议室"},
                "depends_on": ["query"],
            },
        ],
        "strategy": "concise",
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "09:00-09:30",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": "09:00-09:30",
                    "title": "OKR 季度复盘",
                    "location": payload.get("location"),
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert "date_expression" not in recorded_inputs[0]
    assert recorded_inputs[1] == {"action": "update", "location": "1号会议室", "event_id": "EVT-20260531-0001"}
    assert state["react_status"] == "success"


def test_real_prompt_shape_query_update_location_protocol_succeeds(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"query","kind":"tool","objective":"查询下周日公司会议",'
            '"tool_name":"manage_company_calendar","action":"query",'
            '"tool_input":{"action":"query","event_type":"meeting","date_expression":"下周日"}},'
            '{"task_id":"update","kind":"tool","objective":"更新查询到的公司会议地点",'
            '"tool_name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","event_id":"<queried_event_id>","location":"1号会议室"},'
            '"depends_on":["query"]}],'
            '"answer_style":"concise"}',
            '{"next_action":"call_tool","task_id":"update","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    assert state["plan_validation"]["validation_status"] == "valid"

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "09:00-09:30",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": "09:00-09:30",
                    "title": "OKR 季度复盘",
                    "location": payload.get("location"),
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert recorded_inputs[0]["end_date"] == "2026-05-31"
    assert recorded_inputs[1] == {"action": "update", "location": "1号会议室", "event_id": "EVT-20260531-0001"}
    assert state["task_results"][-1]["tool_result"]["event"]["location"] == "1号会议室"
    assert state["react_status"] == "success"


def test_planner_tool_name_alias_name_and_depends_on_action_alias_are_normalized(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"update_company_event_location","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"kind":"tool","name":"manage_company_calendar","action":"query",'
            '"tool_input":{"action":"query","event_type":"meeting","date_expression":"下周日"}},'
            '{"kind":"tool","name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","event_id":"{{depends_on.0.event_id}}","location":"1号会议室"},'
            '"depends_on":["query"]}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    query_task, update_task = state["execution_plan"]["tasks"]
    assert query_task["tool"] == "manage_company_calendar"
    assert query_task["tool_name"] == "manage_company_calendar"
    assert query_task["tool_input"]["start_date"] == "2026-05-31"
    assert update_task["depends_on"] == [query_task["task_id"]]
    assert state["plan_validation"]["validation_status"] == "valid"
    assert state["plan_validation"]["blocked_tasks"] == []


def test_real_trace_shape_name_alias_query_update_executes(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"修改公司会议地点","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"kind":"tool","name":"manage_company_calendar","action":"query",'
            '"tool_input":{"action":"query","event_type":"meeting","date_expression":"下周日"},"task_id":"query_meeting"},'
            '{"kind":"tool","name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","event_id":"pending_from_query_meeting","location":"5号会议室"},'
            '"depends_on":["query_meeting"],"task_id":"update_location"}],'
            '"answer_style":"step_by_step"}',
            '{"next_action":"call_tool","task_id":"update_location","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成5号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "09:00-09:30",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": "09:00-09:30",
                    "title": "OKR 季度复盘",
                    "location": payload.get("location"),
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert recorded_inputs[1] == {"action": "update", "location": "5号会议室", "event_id": "EVT-20260531-0001"}
    assert state["react_status"] == "success"


def test_real_llm_query_update_with_update_date_expression_executes_once_then_update(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"修改下周日的公司会议时间至晚上九点到九点半","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"tool","objective":"查询下周日的公司会议事件，以获取 event_id 和当前安排",'
            '"tool_name":"manage_company_calendar","action":"query","time_expression":"下周日",'
            '"tool_input":{"action":"query","event_type":"meeting","date_expression":"下周日"},"depends_on":[]},'
            '{"task_id":"t2","kind":"tool","objective":"更新查到的公司会议时间至晚上九点到九点半",'
            '"tool_name":"manage_company_calendar","action":"update","depends_on":["t1"],'
            '"tool_input":{"action":"update","event_id":null,"time":"21:00-21:30","date_expression":"下周日"}}],'
            '"answer_style":"step-by-step"}',
            '{"next_action":"call_tool","task_id":"t2","tool_name":"manage_company_calendar"}',
            "已根据工具结果更新会议时间。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议改到晚上九点到九点半", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "16:00-17:00",
                        "title": "OKR 季度复盘",
                        "location": "线上会议",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": payload.get("time"),
                    "title": "OKR 季度复盘",
                    "location": "线上会议",
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert [payload["action"] for payload in recorded_inputs] == ["query", "update"]
    assert recorded_inputs[1]["event_id"] == "EVT-20260531-0001"
    assert recorded_inputs[1]["time"] == "21:00-21:30"
    assert "date_expression" not in recorded_inputs[1]
    assert state["react_status"] == "success"


def test_validation_blocked_calendar_write_does_not_allow_false_success() -> None:
    packet = build_answer_packet(
        {
            "route": "direct",
            "intent": "permission_required",
            "question": "把下周日的公司会议地点改成5号会议室",
            "execution_plan": {"tasks": [], "strategy": "concise"},
            "plan_validation": {
                "validation_status": "refused",
                "blocked_tasks": [
                    {
                        "task_id": "update_location",
                        "kind": "tool",
                        "tool": "manage_company_calendar",
                        "tool_name": "manage_company_calendar",
                        "action": "update",
                        "tool_input": {"action": "update", "event_id": "pending_from_query", "location": "5号会议室"},
                    }
                ],
            },
            "task_results": [],
            "final_answer": "已将会议地点更新为5号会议室。",
        }
    )

    assert not packet.messages
    assert any(isinstance(item, dict) and item.get("类型") == "write_not_executed" for item in packet.task_results)


def test_query_then_update_time_expands_and_updates_only_time(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"calendar_write","kind":"tool","objective":"查询下周日公司会议并更新会议时间",'
            '"tool_name":"manage_company_calendar","action":"query_then_update","time_expression":"下周日",'
            '"tool_input":{"target":{"event_type":"meeting","department":"all"},'
            '"pending_update":{"time":"21:00-21:30"}}}],'
            '"answer_style":"concise"}',
            '{"next_action":"call_tool","task_id":"calendar_write_update","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议改到晚上九点到九点半。", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    assert [task["action"] for task in state["execution_plan"]["tasks"]] == ["query", "update"]
    assert state["execution_plan"]["tasks"][1]["tool_input"]["pending_update"] == {"time": "21:00-21:30"}

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["action"] for task in tasks] == ["query", "update"]
    assert tasks[0]["tool_input"]["start_date"] == "2026-05-31"
    assert tasks[1]["tool_input"]["pending_update"] == {"time": "21:00-21:30"}
    assert "date" not in tasks[1]["tool_input"]
    assert "event_id" not in tasks[1]["tool_input"]

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "16:00-17:00",
                        "title": "OKR 季度复盘",
                        "location": "31号会议室",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": payload.get("time"),
                    "title": "OKR 季度复盘",
                    "location": "31号会议室",
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[0]["start_date"] == "2026-05-31"
    assert recorded_inputs[1]["event_id"] == "EVT-20260531-0001"
    assert recorded_inputs[1]["time"] == "21:00-21:30"
    assert "date" not in recorded_inputs[1]
    assert "location" not in recorded_inputs[1]
    assert "title" not in recorded_inputs[1]
    assert state["react_status"] == "success"


def test_query_then_update_title_expands_and_updates_only_title(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"calendar_write","kind":"tool","objective":"查询下周日公司会议并更新标题",'
            '"tool_name":"manage_company_calendar","action":"query_then_update","time_expression":"下周日",'
            '"tool_input":{"target":{"event_type":"meeting","department":"all"},'
            '"pending_update":{"title":"OKR 年中复盘会"}}}],'
            '"answer_style":"concise"}',
            '{"next_action":"call_tool","task_id":"calendar_write_update","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议标题改成 OKR 年中复盘会。", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    assert state["execution_plan"]["tasks"][1]["tool_input"]["pending_update"] == {"title": "OKR 年中复盘会"}

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        if payload.get("action") == "query":
            call_state["tool_result"] = {
                "action": "query",
                "status": "ok",
                "events": [
                    {
                        "event_id": "EVT-20260531-0001",
                        "date": "2026-05-31",
                        "weekday_zh": "星期日",
                        "time": "16:00-17:00",
                        "title": "OKR 季度复盘",
                        "location": "31号会议室",
                    }
                ],
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": "16:00-17:00",
                    "title": payload.get("title"),
                    "location": "31号会议室",
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs[1] == {"action": "update", "title": "OKR 年中复盘会", "event_id": "EVT-20260531-0001"}
    assert state["react_status"] == "success"


def test_followup_update_with_planner_task_inherits_context_without_slot_extraction(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"update","kind":"tool","objective":"更新上一轮会议地点",'
            '"tool_name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","pending_update":{"location":"3号会议室"}},'
            '"depends_on":[]}],"answer_style":"concise"}',
            '{"next_action":"call_tool","task_id":"update","tool_name":"manage_company_calendar"}',
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把这个会议地点改成 3 号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["previous_tool_context"] = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "events": [
            {
                "event_id": "EVT-20260531-0001",
                "date": "2026-05-31",
                "weekday_zh": "星期日",
                "time": "16:00-17:00",
                "title": "OKR 季度复盘",
                "location": "31号会议室",
            }
        ],
    }

    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["action"] for task in tasks] == ["update"]
    assert tasks[0]["tool_input"]["event_id"] == "EVT-20260531-0001"
    assert tasks[0]["tool_input"]["pending_update"] == {"location": "3号会议室"}

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append({key: value for key, value in payload.items() if not str(key).startswith("_")})
        call_state["tool_result"] = {
            "action": "update",
            "status": "updated",
            "event": {
                "event_id": payload.get("event_id"),
                "date": "2026-05-31",
                "weekday_zh": "星期日",
                "time": "16:00-17:00",
                "title": "OKR 季度复盘",
                "location": payload.get("location"),
            },
        }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert recorded_inputs == [{"action": "update", "event_id": "EVT-20260531-0001", "location": "3号会议室"}]
    assert state["react_status"] == "success"


def test_query_then_update_multiple_candidates_requires_clarification(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(
        make_settings(tmp_path),
        llm=QueueLLM(['{"next_action":"call_tool","task_id":"calendar_write_update","tool_name":"manage_company_calendar"}']),
    )
    state = create_initial_state("把下周的公司会议改到晚上九点。", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "calendar_write",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "下周",
                "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
            },
            {
                "task_id": "calendar_write_update",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "pending_update": {"time": "21:00"}},
                "depends_on": ["calendar_write"],
            },
        ],
        "strategy": "concise",
    }
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        assert payload.get("action") == "query"
        call_state["tool_result"] = {
            "action": "query",
            "status": "ok",
            "events": [
                {"event_id": "EVT-20260525-0001", "date": "2026-05-25", "title": "会议A"},
                {"event_id": "EVT-20260526-0002", "date": "2026-05-26", "title": "会议B"},
            ],
        }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert [payload["action"] for payload in recorded_inputs] == ["query"]
    assert state["react_status"] == "need_clarification"
    assert state["task_results"][-1]["status"] == "needs_clarification"


def test_query_then_update_zero_candidates_does_not_update_or_false_success(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(
        make_settings(tmp_path),
        llm=QueueLLM(['{"next_action":"call_tool","task_id":"calendar_write_update","tool_name":"manage_company_calendar"}']),
    )
    state = create_initial_state("把明天的公司会议改到晚上九点。", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "calendar_write",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "明天",
                "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
            },
            {
                "task_id": "calendar_write_update",
                "kind": "tool",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "pending_update": {"time": "21:00"}},
                "depends_on": ["calendar_write"],
            },
        ],
        "strategy": "concise",
    }
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    recorded_inputs: list[dict] = []

    def fake_call_tool(call_state: dict) -> dict:
        payload = dict(call_state.get("tool_input") or {})
        recorded_inputs.append(payload)
        call_state["tool_result"] = {"action": "query", "status": "ok", "events": []}
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = nodes.react_execute(state)

    assert [payload["action"] for payload in recorded_inputs] == ["query"]
    assert state["react_status"] == "success"
    assert state["task_results"][-1]["status"] == "skipped"
    packet = build_answer_packet(state)
    assert any(
        isinstance(item, dict) and item.get("类型") == "write_not_executed"
        for item in packet.task_results
    )


def test_tool_call_kind_alias_is_normalized_and_not_dropped(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"calendar_write","kind":"tool_call","objective":"查询下周日公司会议并更新地点",'
            '"tool_name":"manage_company_calendar","action":"query_then_update","time_expression":"下周日",'
            '"tool_input":{"target":{"event_type":"meeting"},"pending_update":{"location":"3号会议室"}}}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成 3 号会议室。", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)

    assert [task["kind"] for task in state["execution_plan"]["tasks"]] == ["tool", "tool"]
    assert [task["action"] for task in state["execution_plan"]["tasks"]] == ["query", "update"]


def test_calendar_write_without_real_tool_result_adds_locked_fact() -> None:
    packet = build_answer_packet(
        {
            "route": "tool",
            "intent": "calendar",
            "question": "把明天的公司会议改到晚上九点。",
            "execution_plan": {
                "tasks": [
                    {
                        "task_id": "update",
                        "kind": "tool",
                        "tool_name": "manage_company_calendar",
                        "tool": "manage_company_calendar",
                        "action": "update",
                        "tool_input": {"action": "update", "event_id": "EVT-20260524-0001", "time": "21:00"},
                    }
                ]
            },
            "task_results": [],
            "final_answer": "已成功更新。",
        }
    )

    locked = [item for item in packet.task_results if isinstance(item, dict) and item.get("类型") == "write_not_executed"]
    assert locked
    assert locked[0]["状态"] == "failed_or_not_executed"


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

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

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
