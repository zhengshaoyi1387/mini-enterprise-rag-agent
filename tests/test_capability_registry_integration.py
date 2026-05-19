from __future__ import annotations

from mini_rag.capabilities.registry import default_capability_registry
from mini_rag.core.contracts import CandidatePlan, RequestContext, TaskResult


def test_registry_exposes_handlers_and_role_filtered_contracts() -> None:
    registry = default_capability_registry()

    assert set(registry.handler_names()) == {
        "datetime",
        "calendar_query",
        "calendar_write",
        "attendance_query",
        "rag_qa",
        "mixed_task",
    }
    employee_visible = {contract.name for contract in registry.visible_contracts(role="employee")}

    assert "calendar_query" in employee_visible
    assert "calendar_write" not in employee_visible


def test_registry_validate_refuses_disallowed_capability_role() -> None:
    registry = default_capability_registry()
    plan = CandidatePlan(route="tool", intent="daily_tool")
    ctx = RequestContext(question="帮我新增一个会议", role="employee")

    result = registry.validate("calendar_write", plan, ctx)

    assert result.status == "refused"
    assert result.issues[0].layer == "validator"


def test_registry_formats_tool_results_without_llm() -> None:
    registry = default_capability_registry()
    ctx = RequestContext(question="今天星期几？", role="employee")
    result = TaskResult(
        task_id="t1",
        kind="tool",
        status="ok",
        result_summary="今天是 2026-05-17，星期日。",
        payload={"current_date": "2026-05-17", "weekday_zh": "星期日"},
    )

    answer = registry.format_answer("datetime", [result], ctx)

    assert answer == "今天是 2026-05-17，星期日。"
