from __future__ import annotations

from mini_rag.planning.coverage_checker import check_goal_coverage
from mini_rag.planning.goal_extractor import extract_goals


def test_goal_extractor_marks_tool_plus_rag_as_mixed_task() -> None:
    classification = {
        "route": "tool",
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "knowledge_requirement": {"should_use_rag": True, "requires_company_knowledge": True},
    }
    execution_plan = {
        "tasks": [
            {
                "task_id": "calendar",
                "kind": "tool",
                "objective": "查询明天会议",
                "tool": "manage_company_calendar",
                "action": "query",
            },
            {
                "task_id": "policy",
                "kind": "rag",
                "objective": "查询出差报销注意事项",
                "query": "出差报销回来要注意什么",
            },
        ]
    }

    goals = extract_goals("我明天有会议吗？如果有，出差报销回来要注意什么？", classification, execution_plan)

    assert [goal.capability for goal in goals] == ["calendar_query", "rag_qa", "mixed_task"]
    assert goals[-1].required_result == "tool_and_rag_results"


def test_coverage_checker_blocks_ready_when_rag_required_but_missing() -> None:
    goals = extract_goals(
        "我明天有会议吗？如果有，出差报销回来要注意什么？",
        {"knowledge_requirement": {"should_use_rag": True}},
        {
            "tasks": [
                {"task_id": "calendar", "kind": "tool", "tool": "manage_company_calendar", "action": "query"},
            ]
        },
    )

    report = check_goal_coverage(goals, execution_plan={"tasks": []}, task_results=[], rag_results=[])

    assert report.ready_to_answer is False
    assert report.is_mixed_task is True
    assert "rag_qa" in report.missing_goal_ids


def test_coverage_checker_requires_each_planned_goal_result() -> None:
    goals = extract_goals(
        "查产品部上周考勤异常，再结合考勤制度说明常见处理方式。",
        {"knowledge_requirement": {"should_use_rag": True}},
        {
            "tasks": [
                {"task_id": "attendance", "kind": "tool", "tool": "query_attendance_summary", "objective": "考勤异常"},
                {"task_id": "policy", "kind": "rag", "query": "考勤异常处理方式"},
            ]
        },
    )

    report = check_goal_coverage(
        goals,
        execution_plan={"tasks": []},
        task_results=[{"task_id": "attendance", "kind": "tool", "status": "ok"}],
        rag_results=[],
    )

    assert report.ready_to_answer is False
    assert report.covered_goal_ids == ("attendance",)
    assert "policy" in report.missing_goal_ids


def test_requires_company_knowledge_does_not_force_rag_goal_without_should_use_rag() -> None:
    goals = extract_goals(
        "查询下周所有公司团建日程",
        {"knowledge_requirement": {"requires_company_knowledge": True, "should_use_rag": False}},
        {
            "tasks": [
                {"task_id": "calendar", "kind": "tool", "tool": "manage_company_calendar", "action": "query"},
            ]
        },
    )

    assert [goal.capability for goal in goals] == ["calendar_query"]
