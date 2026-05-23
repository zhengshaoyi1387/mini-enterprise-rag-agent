from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state
from mini_rag.skills.executor import SkillExecutor
from mini_rag.skills.loader import SkillLoader
from mini_rag.skills.registry import SkillRegistry
from mini_rag.tools.contracts import validate_tool_input
from mini_rag.tools.daily_tools import build_default_tool_registry


class Message:
    def __init__(self, content: str):
        self.content = content


class InspectingLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.contents:
            return Message(self.contents.pop(0))
        return Message("已完成。")


def _settings(tmp_path: Path, db_path: Path | None = None) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        ENTERPRISE_DB_PATH=db_path or (tmp_path / "enterprise_demo.db"),
        RERANK_ENABLED=False,
    )


def _runtime_context(db_path: Path, permissions: list[str] | None = None) -> dict[str, object]:
    return {
        "user_id": "u004",
        "role": "hr",
        "enterprise_db_path": str(db_path),
        "permissions": ["attendance:read"] if permissions is None else permissions,
    }


def test_skill_registry_discovers_cards_and_loads_instruction() -> None:
    registry = SkillRegistry.from_base_dir("skills")

    names = {card.name for card in registry.list_skill_cards()}

    assert {"attendance_insight", "policy_gap_checker"} <= names
    card = registry.get_skill_card("attendance_insight")
    assert card is not None
    assert card.risk_level == "read_only"
    assert "attendance:read" in card.required_permissions
    assert "start_date" in card.input_schema_summary["properties"]

    candidates = registry.find_candidate_skills("统计上周考勤异常", intent_tags=["attendance"])
    assert candidates
    assert candidates[0]["name"] == "attendance_insight"
    assert candidates[0]["match_reason"]

    instruction = SkillLoader(registry).load_instruction("attendance_insight")
    assert instruction.ok is True
    assert "统计分析" in instruction.content


def test_attendance_insight_executes_with_permission_and_trace(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    executor = SkillExecutor(SkillRegistry.from_base_dir("skills"))

    result = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {
                "start_date": "2026-05-11",
                "end_date": "2026-05-17",
                "group_by": "employee",
            },
            "runtime_context": _runtime_context(db_path),
        }
    )

    assert result["ok"] is True
    assert result["skill_name"] == "attendance_insight"
    assert result["result"]["period"] == {"start_date": "2026-05-11", "end_date": "2026-05-17"}
    payload = result["result"]
    assert payload["total_abnormal_records"] > 0
    assert payload["items"]
    assert payload["overview"]["total_abnormal_records"] == payload["total_abnormal_records"]
    assert payload["rankings"]["top_abnormal_employees"]
    assert payload["suggested_followups"]
    assert any(item["type"] == "repeated_late" for item in payload["patterns"])
    assert any(item["type"] == "mixed_abnormal" for item in payload["patterns"])
    assert result["trace"]["validated_input"] is True
    assert result["trace"]["validated_output"] is True
    assert any(item["phase"] == "executed" and item["ok"] for item in result["trace"]["events"])


def test_attendance_insight_resolves_relative_enterprise_db_path_before_skill_cwd(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    relative_db_path = Path("data") / "enterprise_demo.db"
    initialize_enterprise_demo_db(relative_db_path, reset=True)
    executor = SkillExecutor(SkillRegistry.from_base_dir(repo_root / "skills"))

    result = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {
                "start_date": "2026-05-11",
                "end_date": "2026-05-17",
                "group_by": "employee",
            },
            "runtime_context": {
                "user_id": "admin",
                "role": "admin",
                "permissions": ["attendance:read"],
                "enterprise_db_path": str(relative_db_path),
            },
        }
    )

    assert result["ok"] is True
    assert result["result"]["total_records"] == 36
    assert result["result"]["total_abnormal_records"] == 8


def test_explicit_attendance_skill_request_exposes_skill_cards_and_executes_skill_run(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    llm = InspectingLLM(
        [
            '{"overall_intent":"attendance","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"tool","objective":"按员工统计上周的考勤异常情况",'
            '"tool_name":"skill","action":"run","time_expression":"上周",'
            '"tool_input":{"action":"run","skill_name":"attendance_insight",'
            '"arguments":{"start_date":"last_week_start","end_date":"last_week_end","group_by":"employee"}},'
            '"depends_on":[]}],"answer_style":"concise"}',
            "已使用 attendance_insight skill 完成统计。",
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path, db_path), llm=llm)
    state = create_initial_state(
        "请使用 attendance_insight skill，按员工统计上周的考勤异常情况。",
        role="hr",
        override_now="2026-05-18T09:30:00+08:00",
    )

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
        nodes.answer_with_llm,
    ):
        state = step(state)

    planner_prompt = llm.calls[0][1][1]
    assert '"name":"skill"' in planner_prompt
    assert '"skill_cards"' in planner_prompt
    assert "attendance_insight" in planner_prompt
    task = state["execution_plan"]["tasks"][0]
    assert task["tool_name"] == "skill"
    assert task["action"] == "run"
    assert task["tool_input"]["skill_name"] == "attendance_insight"
    assert task["tool_input"]["arguments"]["start_date"] == "2026-05-11"
    assert task["tool_input"]["arguments"]["end_date"] == "2026-05-17"
    result = state["task_results"][0]
    assert result["tool_name"] == "skill"
    assert result["skill_name"] == "attendance_insight"
    assert result["skill_result"]["ok"] is True
    assert result["skill_trace"]["validated_input"] is True
    assert result["skill_trace"]["validated_output"] is True


def test_skill_run_uses_resolved_time_over_planner_computed_dates(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    llm = InspectingLLM(
        [
            '{"overall_intent":"attendance","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"tool","objective":"按员工统计上周的考勤异常情况",'
            '"tool_name":"skill","action":"run","time_expression":"上周",'
            '"tool_input":{"action":"run","skill_name":"attendance_insight",'
            '"arguments":{"start_date":"2026-05-14","end_date":"2026-05-20","group_by":"employee"}},'
            '"depends_on":[]}],"answer_style":"concise"}',
            "已使用 attendance_insight skill 完成统计。",
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path, db_path), llm=llm)
    state = create_initial_state(
        "请使用 attendance_insight skill，按员工统计上周的考勤异常情况。",
        role="hr",
        override_now="2026-05-21T22:09:00+08:00",
    )

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
        nodes.answer_with_llm,
    ):
        state = step(state)

    task_args = state["execution_plan"]["tasks"][0]["tool_input"]["arguments"]
    assert task_args["start_date"] == "2026-05-11"
    assert task_args["end_date"] == "2026-05-17"
    skill_payload = state["task_results"][0]["skill_result"]["result"]
    assert skill_payload["period"] == {"start_date": "2026-05-11", "end_date": "2026-05-17"}
    assert skill_payload["total_abnormal_records"] > 0


def test_planner_stage_strips_computed_dates_from_skill_arguments(tmp_path: Path) -> None:
    llm = InspectingLLM(
        [
            '{"overall_intent":"attendance","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"tool","objective":"按员工统计上周的考勤异常情况",'
            '"tool_name":"skill","action":"run","time_expression":"上周",'
            '"tool_input":{"action":"run","skill_name":"attendance_insight",'
            '"arguments":{"start_date":"2026-05-14","end_date":"2026-05-20","group_by":"employee"}},'
            '"depends_on":[]}],"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path), llm=llm)
    state = create_initial_state(
        "请使用 attendance_insight skill，按员工统计上周的考勤异常情况。",
        role="hr",
        override_now="2026-05-21T22:09:00+08:00",
    )

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)

    args = state["execution_plan"]["tasks"][0]["tool_input"]["arguments"]
    assert "start_date" not in args
    assert "end_date" not in args
    assert args["group_by"] == "employee"


def test_attendance_detail_query_keeps_raw_attendance_tool_not_skill(tmp_path: Path) -> None:
    llm = InspectingLLM(
        [
            '{"overall_intent":"attendance","requires_tools":true,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"tool","objective":"查询上周考勤异常明细",'
            '"tool_name":"query_attendance_summary","action":"query","time_expression":"上周",'
            '"tool_input":{"status_filters":["late","leave","absent"],"include_records":true,"group_by":"employee"},'
            '"depends_on":[]}],"answer_style":"concise"}'
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path), llm=llm)
    state = create_initial_state(
        "查一下上周有哪些员工存在考勤异常，给我明细。",
        role="hr",
        override_now="2026-05-18T09:30:00+08:00",
    )

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    task = state["execution_plan"]["tasks"][0]
    assert task["tool_name"] == "query_attendance_summary"
    assert task["tool_name"] != "skill"


def test_attendance_insight_validation_and_permission_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    executor = SkillExecutor(SkillRegistry.from_base_dir("skills"))

    missing_slot = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {"end_date": "2026-05-17"},
            "runtime_context": _runtime_context(db_path),
        }
    )
    assert missing_slot["ok"] is False
    assert missing_slot["error"]["type"] == "validation_error"

    no_permission = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
            "runtime_context": _runtime_context(db_path, permissions=[]),
        }
    )
    assert no_permission["ok"] is False
    assert no_permission["error"]["type"] == "permission_denied"


def test_policy_gap_checker_reports_covered_and_missing_slots() -> None:
    executor = SkillExecutor(SkillRegistry.from_base_dir("skills"))

    result = executor.execute(
        {
            "skill_name": "policy_gap_checker",
            "arguments": {
                "question": "出差酒店费用可以报销吗？流程是什么？",
                "evidence_items": [
                    {
                        "source_id": "finance_001",
                        "title": "差旅报销制度",
                        "content": "报销材料包括行程单、发票、支付凭证。审批流程为直属负责人审批后提交财务复核。",
                    }
                ],
                "required_slots": ["是否可报销", "报销材料", "审批流程"],
            },
            "runtime_context": {"role": "employee", "permissions": ["rag:read"]},
        }
    )

    assert result["ok"] is True
    payload = result["result"]
    covered = {item["slot"] for item in payload["covered_slots"] if item.get("coverage_level") == "full"}
    partial = {item["slot"] for item in payload.get("partial_slots", [])}
    missing = {item["slot"] for item in payload["missing_slots"]}
    assert "报销材料" in covered | partial
    assert "审批流程" in covered | partial
    assert "是否可报销" in missing
    assert payload["overall"] == "partial"
    assert "answer" not in payload


def test_skill_tool_adapter_is_registered_without_removing_core_tools(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    registry = build_default_tool_registry()

    assert registry.has_tool("skill")
    assert registry.has_tool("manage_company_calendar")
    assert registry.has_tool("query_attendance_summary")

    payload = validate_tool_input(
        "skill",
        {
            "action": "run",
            "skill_name": "attendance_insight",
            "arguments": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
            "runtime_context": _runtime_context(db_path),
        },
    )
    result = registry.invoke("skill", payload)

    assert result["ok"] is True
    assert result["action"] == "run"
    assert result["skill_name"] == "attendance_insight"
    assert result["result"]["total_abnormal_records"] > 0
