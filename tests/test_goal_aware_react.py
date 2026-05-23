from __future__ import annotations

from pathlib import Path

from mini_rag.answer.packet import build_answer_packet
from mini_rag.config import Settings
from mini_rag.graph.workflow import AgenticRAGWorkflow
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state


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


def _planner_query_only_with_goal(expected_result: dict) -> str:
    return (
        '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
        '"goal_contract":{"goal_type":"calendar_update",'
        '"target":{"event_type":"meeting","time_expression":"下周日"},'
        '"expected_result":'
        + __import__("json").dumps(expected_result, ensure_ascii=False, separators=(",", ":"))
        + ',"success_condition":{"required_tool":"manage_company_calendar","required_action":"update",'
        '"required_status":"updated","updated_fields_must_match":true}},'
        '"tasks":[{"task_id":"query","kind":"tool","objective":"查询下周日公司会议",'
        '"tool_name":"manage_company_calendar","action":"query","time_expression":"下周日",'
        '"tool_input":{"action":"query","event_type":"meeting"}}],'
        '"answer_style":"concise"}'
    )


def _run_query_only_goal_case(tmp_path: Path, *, expected_result: dict, events: list[dict]) -> dict:
    llm = QueueLLM([_planner_query_only_with_goal(expected_result)])
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议改到晚上九点到十点", role="admin", override_now="2026-05-23T03:00:00+08:00")
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
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "events": events,
            }
        else:
            call_state["tool_result"] = {
                "action": "update",
                "status": "updated",
                "event": {
                    "event_id": payload.get("event_id"),
                    "date": payload.get("date") or "2026-05-31",
                    "weekday_zh": "星期日",
                    "time": payload.get("time") or "16:00-17:00",
                    "title": "OKR 季度复盘",
                    "location": payload.get("location") or "线上会议",
                },
            }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]
    state = nodes.react_execute(state)
    state["_recorded_inputs"] = recorded_inputs
    return state


def test_goal_aware_react_adds_safe_update_when_planner_only_queries_unique_event(tmp_path: Path) -> None:
    state = _run_query_only_goal_case(
        tmp_path,
        expected_result={"time": "21:00-22:00"},
        events=[
            {
                "event_id": "EVT-20260531-0001",
                "date": "2026-05-31",
                "weekday_zh": "星期日",
                "time": "16:00-17:00",
                "title": "OKR 季度复盘",
                "location": "线上会议",
            }
        ],
    )

    assert [payload["action"] for payload in state["_recorded_inputs"]] == ["query", "update"]
    assert state["_recorded_inputs"][1] == {"action": "update", "event_id": "EVT-20260531-0001", "time": "21:00-22:00"}
    assert state["completion_check"]["status"] == "completed"
    assert state["completion_check"]["safe_next_action_source"] == "deterministic"
    assert state["react_status"] == "success"


def test_goal_aware_react_does_not_update_when_expected_result_missing(tmp_path: Path) -> None:
    state = _run_query_only_goal_case(
        tmp_path,
        expected_result={},
        events=[
            {
                "event_id": "EVT-20260531-0001",
                "date": "2026-05-31",
                "weekday_zh": "星期日",
                "time": "16:00-17:00",
                "title": "OKR 季度复盘",
                "location": "线上会议",
            }
        ],
    )

    assert [payload["action"] for payload in state["_recorded_inputs"]] == ["query"]
    assert state["completion_check"]["status"] in {"incomplete", "needs_clarification"}
    assert state["completion_assessment"]["ready_to_answer"] is False


def test_goal_aware_react_marks_not_found_without_update(tmp_path: Path) -> None:
    state = _run_query_only_goal_case(tmp_path, expected_result={"time": "21:00"}, events=[])

    assert [payload["action"] for payload in state["_recorded_inputs"]] == ["query"]
    assert state["completion_check"]["status"] == "failed"
    assert state["completion_check"]["reason"] == "not_found"
    assert state["react_status"] == "failed"


def test_goal_aware_react_requires_clarification_for_multiple_events(tmp_path: Path) -> None:
    state = _run_query_only_goal_case(
        tmp_path,
        expected_result={"time": "21:00"},
        events=[
            {"event_id": "EVT-20260531-0001", "date": "2026-05-31", "time": "16:00-17:00", "title": "OKR 季度复盘"},
            {"event_id": "EVT-20260531-0002", "date": "2026-05-31", "time": "18:00-19:00", "title": "研发例会"},
        ],
    )

    assert [payload["action"] for payload in state["_recorded_inputs"]] == ["query"]
    assert state["completion_check"]["status"] == "needs_clarification"
    assert state["react_status"] == "need_clarification"


def test_goal_aware_completion_rejects_update_field_mismatch(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"goal_contract":{"goal_type":"calendar_update","expected_result":{"time":"21:00-22:00"}},'
            '"tasks":[{"task_id":"update","kind":"tool","objective":"更新会议时间",'
            '"tool_name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","event_id":"EVT-20260531-0001","time":"21:00-22:00"}}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把这个会议改到晚上九点到十点", role="admin", override_now="2026-05-23T03:00:00+08:00")
    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    def fake_call_tool(call_state: dict) -> dict:
        call_state["tool_result"] = {
            "action": "update",
            "status": "updated",
            "event": {
                "event_id": "EVT-20260531-0001",
                "date": "2026-05-31",
                "time": "16:00-17:00",
                "title": "OKR 季度复盘",
            },
        }
        nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    nodes._call_tool = fake_call_tool  # type: ignore[method-assign]
    state = nodes.react_execute(state)
    packet = build_answer_packet({**state, "final_answer": "已更新会议时间。"})

    assert state["completion_check"]["status"] == "failed"
    assert state["completion_check"]["reason"] == "updated_field_mismatch"
    assert state["completion_assessment"]["ready_to_answer"] is False
    assert any(isinstance(item, dict) and item.get("类型") == "write_not_executed" for item in packet.task_results)


def test_langgraph_workflow_preserves_goal_contract_and_completion_fields(tmp_path: Path) -> None:
    llm = QueueLLM([_planner_query_only_with_goal({"location": "1号会议室"}), "已根据 completion_check 输出回答。"])
    workflow = AgenticRAGWorkflow(make_settings(tmp_path), llm=llm)
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
                    "time": "16:00-17:00",
                    "title": "OKR 季度复盘",
                    "location": payload.get("location"),
                },
            }
        workflow.nodes._record_tool_task_result(call_state, before_tool_calls=len(call_state.get("tool_calls") or []))
        return call_state

    workflow.nodes._call_tool = fake_call_tool  # type: ignore[method-assign]

    state = workflow.run(
        "把下周日的公司会议地点改成 1号会议室",
        session_id="goal-state-preserve",
        user_id="tester",
        role="admin",
        override_now="2026-05-23T03:00:00+08:00",
    )

    assert [payload["action"] for payload in recorded_inputs] == ["query", "update"]
    assert state["goal_contract"]["goal_type"] == "calendar_update"
    assert state["completion_check"]["status"] == "completed"


def test_skill_tool_action_is_normalized_to_run_even_if_planner_says_analyze(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"attendance_analysis","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"tool","tool_name":"skill","action":"analyze",'
            '"time_expression":"上周","tool_input":{"action":"analyze","skill_name":"attendance_insight",'
            '"arguments":{"group_by":"employee"}}}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("请使用 attendance_insight skill，按员工统计上周的考勤异常情况。", role="hr", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)

    task = state["execution_plan"]["tasks"][0]
    assert task["action"] == "run"
    assert task["tool_input"]["action"] == "run"


def test_goal_contract_does_not_treat_query_date_as_location_update_field(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"goal_contract":{"goal_type":"calendar_update","expected_result":{"location":"1号会议室","date_expression":"下周日"}},'
            '"tasks":[{"task_id":"query","kind":"tool","tool_name":"manage_company_calendar","action":"query",'
            '"time_expression":"下周日","tool_input":{"action":"query","event_type":"meeting"}},'
            '{"task_id":"update","kind":"tool","tool_name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","event_id":"<queried_event_id>","location":"1号会议室","date_expression":"下周日"},'
            '"depends_on":["query"]}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)

    assert state["goal_contract"]["expected_result"] == {"location": "1号会议室"}


def test_goal_contract_does_not_treat_query_event_type_as_update_field(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"calendar","requires_tools":true,"requires_rag":false,'
            '"goal_contract":{"goal_type":"calendar_update","expected_result":{"location":"1号会议室","type":"meeting"}},'
            '"tasks":[{"task_id":"query","kind":"tool","tool_name":"manage_company_calendar","action":"query",'
            '"time_expression":"下周日","tool_input":{"action":"query","event_type":"meeting"}},'
            '{"task_id":"update","kind":"tool","tool_name":"manage_company_calendar","action":"update",'
            '"tool_input":{"action":"update","event_id":"<queried_event_id>","location":"1号会议室","type":"meeting"},'
            '"depends_on":["query"]}],'
            '"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("把下周日的公司会议地点改成 1号会议室", role="admin", override_now="2026-05-23T03:00:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)

    assert state["goal_contract"]["expected_result"] == {"location": "1号会议室"}
