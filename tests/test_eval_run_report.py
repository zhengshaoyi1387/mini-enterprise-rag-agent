from __future__ import annotations

from pathlib import Path

from mini_rag.eval.failure_classifier import FailureClassification
from mini_rag.eval.run_report import render_eval_report, render_run_report, write_eval_report


def test_eval_markdown_report_contains_category_stats_and_failed_case_summary(tmp_path: Path) -> None:
    classifications = [
        FailureClassification(
            case_id="rag_001",
            passed=False,
            failure_category="rag_evidence_error",
            failure_categories=("rag_evidence_error",),
            reason="检索到了 finance 报销制度候选文档，但 verifier 判 empty。",
            node_hint="capabilities/rag/verifier.py",
            fix_hint="检查中文短 query 的 evidence relevance 规则",
            question="介绍公司的报销制度",
            expected_brief="应回答报销制度",
            actual_brief="证据不足",
            trace_path="logs/traces/trace.json",
        ),
        FailureClassification(case_id="ok_001", passed=True, failure_category="passed"),
        FailureClassification(case_id="infra_001", passed=False, failure_category="infra_error", failure_categories=("infra_error",), reason="403 quota"),
    ]
    config = {"fixed_now": "2026-05-17T01:00:00+08:00", "model": "qwen", "rerank_enabled": False, "max_cases": 3, "suite": "unit"}

    markdown = render_eval_report(classifications, config=config)
    path = write_eval_report(classifications, output_dir=tmp_path, config=config, generated_at="20260519_120000")

    assert path == tmp_path / "eval_report_20260519_120000.md"
    assert path.exists()
    assert "total_cases" in markdown
    assert "agent_failed_cases" in markdown
    assert "rag_evidence_error" in markdown
    assert "rag_001" in markdown
    assert "capabilities/rag/verifier.py" in markdown
    assert "fixed_now" in markdown


def test_run_report_summarizes_single_trace_and_issue_classification() -> None:
    trace = {
        "trace_id": "abc",
        "question": "介绍公司的报销制度",
        "execution_plan": {"tasks": [{"task_id": "rag", "kind": "rag", "query": "公司报销制度"}]},
        "resolved_time_facts": [],
        "react_steps": [{"step": 1, "action": "search_rag", "status": "empty"}],
        "tool_calls": [{"tool_name": "search_knowledge_base", "args": {"query": "公司报销制度"}}],
        "task_results": [{"task_id": "rag", "kind": "rag", "status": "empty"}],
        "executed_queries": ["公司报销制度"],
        "answer": "当前可访问知识库未找到明确依据。",
        "candidate_sources": [{"source": "finance/finance_01_reimbursement_travel_procurement_2026.md"}],
        "sources": [],
    }
    classification = FailureClassification(
        case_id="abc",
        passed=False,
        failure_category="rag_evidence_error",
        reason="相关候选未进入 supporting sources。",
        node_hint="capabilities/rag/verifier.py",
    )

    markdown = render_run_report(trace, classification=classification)

    assert "abc" in markdown
    assert "Planner tasks" in markdown
    assert "RAG queries" in markdown
    assert "rag_evidence_error" in markdown
    assert "capabilities/rag/verifier.py" in markdown
