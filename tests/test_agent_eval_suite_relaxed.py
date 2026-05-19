from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent_eval_suite_relaxed.py"
spec = importlib.util.spec_from_file_location("agent_eval_suite_relaxed", SCRIPT)
agent_eval_suite_relaxed = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = agent_eval_suite_relaxed
spec.loader.exec_module(agent_eval_suite_relaxed)


def test_e2e_rule_fails_skipped_task_when_task_success_expected() -> None:
    case = {
        "id": "e2e_skipped",
        "question": "先查下周团建，再把第一个改成高层会议",
        "expected": {
            "task_success": True,
            "expected_tools": [["manage_company_calendar", "query"]],
            "must_contain": ["高层会议"],
        },
    }
    trace = {
        "route": "tool",
        "tool_calls": [{"tool_name": "manage_company_calendar", "action": "query", "ok": True, "args": {}}],
        "task_results": [
            {
                "task_id": "t1",
                "kind": "tool",
                "status": "ok",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_result": {"events": []},
            },
            {
                "task_id": "t2",
                "kind": "tool",
                "status": "skipped",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_result": {"status": "skipped"},
            },
        ],
        "answer": "没有匹配日程可更新。",
    }

    scores, failures = agent_eval_suite_relaxed.evaluate_e2e_rule(case, {"answer": trace["answer"]}, trace, 10)

    assert scores["actual_success_no_blocked_tasks"] is False
    assert "actual_success_no_blocked_tasks" in failures
    assert scores["answer_must_contain_hit"] is False
    assert "answer_must_contain_hit" in failures


def test_evaluate_case_with_both_judge_fails_when_llm_task_success_zero(monkeypatch) -> None:
    case = {
        "id": "e2e_llm_zero",
        "question": "查询并更新日程",
        "expected": {"task_success": True},
    }
    trace = {
        "route": "tool",
        "tool_calls": [{"tool_name": "manage_company_calendar", "action": "query", "ok": True, "args": {}}],
        "task_results": [
            {
                "task_id": "t1",
                "kind": "tool",
                "status": "ok",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_result": {"events": []},
            }
        ],
        "answer": "已查询。",
    }
    monkeypatch.setattr(
        agent_eval_suite_relaxed,
        "judge_answer_with_llm",
        lambda *_args, **_kwargs: {"task_success": 0, "answer_correctness": 0},
    )
    args = argparse.Namespace(judge="both", role="employee", llm_judge_model=None, judge_failed_only=False, judge_sample_rate=1.0)

    result = agent_eval_suite_relaxed.evaluate_case(
        "e2e",
        case,
        {"answer": trace["answer"], "trace": trace},
        10,
        args,
        settings=None,
    )

    assert result.passed is False
    assert result.actual_success is False
    assert "llm judge task_success=0" in result.failure_reasons
    assert "actual_success=false" in result.failure_reasons


def test_evaluate_case_with_both_judge_accepts_expected_refusal_task_success_zero(monkeypatch) -> None:
    case = {
        "id": "e2e_expected_refusal",
        "question": "删除明天会议",
        "expected": {
            "task_success": False,
            "should_refuse": True,
            "must_contain": ["无权", "权限"],
            "must_not_contain": ["已删除"],
        },
    }
    trace = {
        "route": "direct",
        "tool_calls": [],
        "task_results": [],
        "answer": "你无权删除公司日程，当前角色权限不足。",
    }
    monkeypatch.setattr(
        agent_eval_suite_relaxed,
        "judge_answer_with_llm",
        lambda *_args, **_kwargs: {
            "task_success": 0,
            "answer_correctness": 1,
            "answer_completeness": 1,
            "refusal_correctness": 1,
            "groundedness": 1,
            "hallucination": 0,
        },
    )
    args = argparse.Namespace(judge="both", role="employee", llm_judge_model=None, judge_failed_only=False, judge_sample_rate=1.0)

    result = agent_eval_suite_relaxed.evaluate_case(
        "e2e",
        case,
        {"answer": trace["answer"], "trace": trace},
        10,
        args,
        settings=None,
    )

    assert result.passed is True
    assert "llm judge task_success=0" not in result.failure_reasons
    assert "actual_success=false" not in result.failure_reasons


def test_e2e_permission_notice_is_not_treated_as_whole_request_refusal() -> None:
    case = {
        "id": "permission_notice",
        "question": "查询明天会议并告诉我能不能删除",
        "expected": {
            "task_success": True,
            "should_refuse": False,
            "expected_tools": [["get_current_datetime", "*"], ["manage_company_calendar", "query"]],
            "must_contain": ["无权", "权限"],
        },
    }
    trace = {
        "route": "tool",
        "tool_calls": [
            {"tool_name": "get_current_datetime", "action": "*", "ok": True, "args": {}},
            {"tool_name": "manage_company_calendar", "action": "query", "ok": True, "args": {}},
        ],
        "task_results": [
            {"task_id": "t1", "kind": "tool", "status": "ok", "tool_name": "manage_company_calendar", "action": "query"}
        ],
        "answer": "明天有公司会议，但你无权删除，当前角色权限不足。",
    }

    scores, failures = agent_eval_suite_relaxed.evaluate_e2e_rule(case, {"answer": trace["answer"]}, trace, 10)

    assert scores["refusal_accuracy"] is True
    assert "refusal_accuracy" not in failures


def test_policy_prohibition_and_permission_source_names_are_not_refusals() -> None:
    answer = (
        "根据 it_01_account_permission_vpn_baseline.md，明确规定不允许员工之间共用账号；"
        "知识库权限不能只在回答阶段过滤，无权限文档片段不应传给模型。"
    )

    assert agent_eval_suite_relaxed.is_refusal_answer(answer) is False
    assert agent_eval_suite_relaxed.refusal_accuracy(False, answer) is True


def test_no_evidence_language_is_detected_as_refusal() -> None:
    answer = "根据现有提供的证据，没有找到具体放假日期及调休安排的信息，因此无法直接回答您的问题。"

    assert agent_eval_suite_relaxed.is_refusal_answer(answer) is True
    assert agent_eval_suite_relaxed.refusal_accuracy(True, answer) is True


def test_no_permission_to_view_or_query_is_detected_as_refusal() -> None:
    answer = "你当前角色无权查看该范围的公司内部考勤数据；部门、全员或明细查询需要 HR 或 admin 权限。"

    assert agent_eval_suite_relaxed.is_refusal_answer(answer) is True
    assert agent_eval_suite_relaxed.refusal_accuracy(True, answer) is True
    assert agent_eval_suite_relaxed.is_refusal_answer("你当前角色无权使用该企业能力，请切换到有权限的账号后再试。") is True


def test_delete_empty_skipped_result_is_not_a_blocking_failure() -> None:
    task_results = [
        {
            "task_id": "delete_calendar",
            "kind": "tool",
            "status": "skipped",
            "tool_name": "manage_company_calendar",
            "action": "delete",
            "result_summary": "没有匹配日程可删除。",
            "tool_result": {"status": "skipped", "message": "没有匹配日程可删除"},
        }
    ]

    assert agent_eval_suite_relaxed.task_results_have_blocking_failures(task_results) is False


def test_infra_error_result_is_not_agent_failure() -> None:
    args = argparse.Namespace(judge="rule", role="employee", llm_judge_model=None)
    result = agent_eval_suite_relaxed.build_error_result(
        "rag",
        {"id": "quota", "question": "制度是什么"},
        args,
        RuntimeError("Error code: 403 - quota exhausted"),
    )

    assert result.infra_error is True
    assert result.actual_success is None
    assert result.passed is False
    assert "infra_error" in result.failure_reasons


def test_summary_separates_infra_from_agent_failures() -> None:
    results = [
        agent_eval_suite_relaxed.EvalCaseResult("rag", "infra", "q1", "employee", False, infra_error=True),
        agent_eval_suite_relaxed.EvalCaseResult("rag", "pass", "q2", "employee", True, actual_success=True),
        agent_eval_suite_relaxed.EvalCaseResult("rag", "fail", "q3", "employee", False, actual_success=False),
    ]

    summary = agent_eval_suite_relaxed.summarize_results(results, "all", "rule")

    assert summary["total_cases"] == 3
    assert summary["infra_error_cases"] == 1
    assert summary["executed_cases"] == 2
    assert summary["agent_passed_cases"] == 1
    assert summary["agent_failed_cases"] == 1
    assert summary["agent_pass_rate"] == 0.5
    assert summary["failure_categories"]["infra_error"] == 1
    assert summary["failure_categories"]["answer_synthesis_error"] == 1


def test_failure_reasons_are_classified_by_evaluator_layer() -> None:
    assert agent_eval_suite_relaxed.classify_failure_category(["route_accuracy"], {}, infra_error=False) == "planning_error"
    assert agent_eval_suite_relaxed.classify_failure_category(["tool_sequence_accuracy"], {}, infra_error=False) == "planning_error"
    assert agent_eval_suite_relaxed.classify_failure_category(["forbidden_argument_pass"], {}, infra_error=False) == "safety_error"
    assert agent_eval_suite_relaxed.classify_failure_category(["actual_success_no_blocked_tasks"], {}, infra_error=False) == "safety_error"
    assert agent_eval_suite_relaxed.classify_failure_category(["expected source not retrieved"], {}, infra_error=False) == "rag_retrieval_error"
    assert agent_eval_suite_relaxed.classify_failure_category(["answer_must_contain_hit"], {}, infra_error=False) == "answer_synthesis_error"
    assert agent_eval_suite_relaxed.classify_failure_category(["infra_error"], {}, infra_error=True) == "infra_error"


def test_fixture_restore_copies_base_files(tmp_path: Path) -> None:
    fixture = tmp_path / "fixtures" / "company_calendar.base.json"
    target = tmp_path / "business" / "company_calendar.json"
    fixture.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    fixture.write_text('[{"event_id":"EVT-20260518-0001","title":"base"}]', encoding="utf-8")
    target.write_text('[{"event_id":"EVT-20260518-0001","title":"dirty"}]', encoding="utf-8")

    restored = agent_eval_suite_relaxed.restore_fixture_pairs([(fixture, target)])

    assert restored == [target]
    assert "base" in target.read_text(encoding="utf-8")


def test_fixture_restore_requires_existing_base_file(tmp_path: Path) -> None:
    fixture = tmp_path / "fixtures" / "missing.base.json"
    target = tmp_path / "business" / "company_calendar.json"

    try:
        agent_eval_suite_relaxed.restore_fixture_pairs([(fixture, target)])
    except FileNotFoundError as exc:
        assert "missing base fixture" in str(exc)
    else:
        raise AssertionError("restore_fixture_pairs should reject missing base fixtures")


def test_eval_text_normalization_handles_dates_weekdays_empty_and_rooms() -> None:
    assert agent_eval_suite_relaxed.normalize_eval_text("2026年5月18日") == "2026-05-18"
    assert agent_eval_suite_relaxed.normalize_eval_text("10:00–12:00") == "10:00-12:00"
    assert agent_eval_suite_relaxed.normalize_eval_text("Sunday") == "星期日"
    assert agent_eval_suite_relaxed.normalize_eval_text("周日") == "星期日"
    assert "empty_result" in agent_eval_suite_relaxed.normalize_eval_text("暂无公司日程")
    assert agent_eval_suite_relaxed.normalize_eval_text("会议室 A") == "会议室a"


def test_llm_judge_defaults_skip_successful_rule_case_when_both() -> None:
    args = argparse.Namespace(judge="both", judge_failed_only=True, judge_sample_rate=0.0)
    case = {"id": "ok"}

    assert agent_eval_suite_relaxed.should_run_llm_judge(args, case, []) is False
    assert agent_eval_suite_relaxed.should_run_llm_judge(args, case, ["tool_accuracy"]) is True


def test_trajectory_fields_are_supported_by_rule_judge() -> None:
    case = {
        "id": "trajectory",
        "question": "查日程",
        "expected_tool": "manage_company_calendar",
        "expected_action": "query",
        "forbidden_actions": [["manage_company_calendar", "delete"]],
        "should_write": False,
        "expected_status": "ok",
    }
    trace = {
        "route": "tool",
        "tool_calls": [{"tool_name": "manage_company_calendar", "action": "query", "ok": True, "args": {}}],
        "task_results": [{"tool_name": "manage_company_calendar", "action": "query", "status": "ok"}],
        "answer": "查询完成。",
    }

    scores, failures = agent_eval_suite_relaxed.evaluate_tool_rule(case, {"answer": trace["answer"]}, trace, 10)

    assert scores["tool_accuracy"] is True
    assert scores["action_accuracy"] is True
    assert scores["forbidden_actions_pass"] is True
    assert scores["expected_status_pass"] is True
    assert failures == []


def test_e2e_tool_sequence_takes_precedence_over_top_level_write_action() -> None:
    case = {
        "id": "delete_empty",
        "question": "删除 2099-01-01 的所有公司会议。",
        "expected": {
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_sequence": [["manage_company_calendar", "query"]],
            "should_write": False,
            "task_success": True,
            "must_not_contain": ["已删除"],
        },
    }
    trace = {
        "route": "tool",
        "tool_calls": [
            {"tool_name": "manage_company_calendar", "action": "query", "ok": True, "args": {"start_date": "2099-01-01"}}
        ],
        "task_results": [
            {
                "task_id": "query_calendar",
                "kind": "tool",
                "status": "ok",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_result": {"events": []},
            },
            {
                "task_id": "delete_calendar",
                "kind": "tool",
                "status": "skipped",
                "tool_name": "manage_company_calendar",
                "action": "delete",
                "tool_result": {"status": "skipped", "message": "没有匹配日程可删除"},
            },
        ],
        "answer": "2099-01-01 没有匹配的公司会议，无需删除。",
    }

    expected = agent_eval_suite_relaxed.expected_from_case(case, suite_type="e2e")
    scores, failures = agent_eval_suite_relaxed.evaluate_e2e_rule(case, {"answer": trace["answer"]}, trace, 10)

    assert expected["expected_tools"] == [["manage_company_calendar", "query"]]
    assert scores["expected_tool_coverage"] is True
    assert scores["task_success"] is True
    assert failures == []
