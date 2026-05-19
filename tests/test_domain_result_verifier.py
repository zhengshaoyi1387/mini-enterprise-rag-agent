from __future__ import annotations

from mini_rag.capabilities.verifier import task_result_quality_issues, terminal_tool_results_require_answer


def test_calendar_query_event_type_mismatch_is_a_quality_issue() -> None:
    plan_tasks = [
        {
            "task_id": "calendar",
            "kind": "tool",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"event_type": "meeting"},
        }
    ]
    task_results = [
        {
            "task_id": "calendar",
            "status": "ok",
            "tool_input": {"event_type": "training"},
            "tool_result": {"status": "ok"},
        }
    ]

    issues = task_result_quality_issues(plan_tasks, task_results)

    assert issues == [
        {
            "task_id": "calendar",
            "status": "contract_mismatch",
            "field": "event_type",
            "planned": "meeting",
            "actual": "training",
        }
    ]


def test_terminal_tool_results_can_answer_without_llm_repair() -> None:
    results = [
        {
            "task_id": "delete",
            "status": "needs_clarification",
            "tool_result": {"status": "needs_clarification"},
        }
    ]

    assert terminal_tool_results_require_answer(results) is True


def test_nonterminal_tool_error_does_not_bypass_completion_assessment() -> None:
    results = [
        {
            "task_id": "delete",
            "status": "error",
            "tool_result": {"error": "unexpected backend failure"},
        }
    ]

    assert terminal_tool_results_require_answer(results) is False
