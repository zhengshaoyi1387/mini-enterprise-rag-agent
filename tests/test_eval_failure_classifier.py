from __future__ import annotations

from mini_rag.eval.failure_classifier import classify_failure


def test_quota_and_403_are_infra_errors() -> None:
    result = classify_failure(
        case_id="quota",
        question="制度是什么",
        expected={},
        actual_answer="",
        trace={},
        tool_calls=[],
        task_results=[],
        execution_plan={},
        sources=[],
        error="Error code: 403 - quota exhausted",
    )

    assert result.failure_category == "infra_error"
    assert "quota" in result.reason.lower() or "403" in result.reason


def test_unresolved_time_fact_is_time_resolution_error() -> None:
    trace = {
        "resolved_time_facts": [
            {"task_id": "t1", "time_expression": "星期一", "kind": "none", "items": []}
        ],
        "execution_plan": {"tasks": [{"task_id": "t1", "time_expression": "星期一"}]},
    }

    result = classify_failure(
        case_id="time",
        question="星期一有什么会议",
        expected={},
        actual_answer="",
        trace=trace,
        tool_calls=[],
        task_results=[],
        execution_plan=trace["execution_plan"],
        sources=[],
        error=None,
    )

    assert result.failure_category == "time_resolution_error"
    assert result.node_hint == "capabilities/datetime/resolver.py"


def test_candidate_finance_source_without_supporting_source_is_rag_evidence_error() -> None:
    trace = {
        "candidate_sources": [
            {
                "source": "finance/finance_01_reimbursement_travel_procurement_2026.md",
                "title_path": "报销、差旅与采购制度 2026",
                "preview": "费用报销需提交发票和审批单。",
            }
        ],
        "sources": [],
    }

    result = classify_failure(
        case_id="rag_evidence",
        question="介绍公司的报销制度",
        expected={},
        actual_answer="当前可访问知识库未找到明确依据。",
        trace=trace,
        tool_calls=[],
        task_results=[{"kind": "rag", "status": "empty", "query": "公司报销制度"}],
        execution_plan={},
        sources=[],
        error=None,
    )

    assert result.failure_category == "rag_evidence_error"
    assert result.node_hint == "capabilities/rag/evidence_judge.py"


def test_correct_tool_result_but_empty_answer_is_answer_synthesis_error() -> None:
    result = classify_failure(
        case_id="answer",
        question="查明天会议",
        expected={},
        actual_answer="",
        trace={},
        tool_calls=[{"tool_name": "manage_company_calendar", "action": "query", "ok": True}],
        task_results=[{"kind": "tool", "status": "ok", "tool_result": {"events": [{"title": "周会"}]}}],
        execution_plan={},
        sources=[],
        error=None,
    )

    assert result.failure_category == "answer_synthesis_error"
    assert result.node_hint == "answer/service.py"


def test_event_id_all_is_safety_error() -> None:
    result = classify_failure(
        case_id="safety",
        question="删除全部会议",
        expected={},
        actual_answer="已删除。",
        trace={},
        tool_calls=[
            {
                "tool_name": "manage_company_calendar",
                "action": "delete",
                "ok": True,
                "args": {"event_id": "all"},
            }
        ],
        task_results=[],
        execution_plan={},
        sources=[],
        error=None,
    )

    assert result.failure_category == "safety_error"
    assert result.node_hint == "capabilities/calendar/validator.py"


def test_valid_calendar_create_time_schema_is_not_tool_input_error() -> None:
    result = classify_failure(
        case_id="create",
        question="创建会议",
        expected={},
        actual_answer="创建失败",
        trace={},
        tool_calls=[],
        task_results=[],
        execution_plan={
            "tasks": [
                {
                    "kind": "tool",
                    "tool_name": "manage_company_calendar",
                    "action": "create",
                    "tool_input": {"date": "2026-05-19", "time": "21:00-22:00", "title": "员工会议"},
                }
            ]
        },
        sources=[],
        error=None,
    )

    assert result.failure_category != "tool_input_error"
