from __future__ import annotations

from mini_rag.planning.compiler import PlanCompiler


def test_plan_compiler_owns_default_plan_and_task_normalization() -> None:
    compiler = PlanCompiler()

    plan = compiler.default_plan_from_classification(
        {
            "route": "tool",
            "selected_tool": "get_current_datetime",
            "selected_action": "*",
            "standalone_query": "今天几号？",
            "time_requirement": {"time_reference_type": "relative", "requires_current_datetime": True},
        },
        question="今天几号？",
    )
    assert plan["execution_plan"]["tasks"][0]["tool"] == "get_current_datetime"
    assert plan["execution_plan"]["tasks"][0]["tool_input"] == {"timezone": "Asia/Shanghai"}

    task = compiler.normalize_execution_task(
        {
            "kind": "tool",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "date": "2026-05-18"},
        },
        0,
    )
    assert task["tool_input"]["start_date"] == "2026-05-18"
    assert task["tool_input"]["end_date"] == "2026-05-18"
    assert "date" not in task["tool_input"]
