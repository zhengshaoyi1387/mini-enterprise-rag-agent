from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from mini_rag.eval.failure_classifier import FailureClassification


def _case_dict(item: FailureClassification | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, FailureClassification):
        return item.to_dict()
    return dict(item)


def _brief(value: Any, limit: int = 260) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _next_steps(counter: Counter[str]) -> list[str]:
    hints = {
        "planning_error": "planning_error 多：优先检查 Planner prompt/schema 和 plan normalization。",
        "time_resolution_error": "time_resolution_error 多：优先修统一 TimeResolver。",
        "tool_input_error": "tool_input_error 多：检查 Validator 与 ToolInput 构造。",
        "rag_retrieval_error": "rag_retrieval_error 多：检查 retrieval_query、KB routing 和 retriever 配置。",
        "rag_evidence_error": "rag_evidence_error 多：检查 verifier/self-correction。",
        "answer_synthesis_error": "answer_synthesis_error 多：检查 AnswerPacket 和 Answer prompt。",
        "safety_error": "safety_error 多：立即检查 calendar write guardrails。",
        "infra_error": "infra_error 多：不计入 Agent failure，先处理外部服务/API/依赖。",
    }
    return [hints[key] for key, _count in counter.most_common() if key in hints][:5]


def render_eval_report(
    classifications: list[FailureClassification | dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
) -> str:
    rows = [_case_dict(item) for item in classifications]
    total = len(rows)
    passed = sum(1 for row in rows if row.get("passed") is True or row.get("failure_category") == "passed")
    infra = sum(1 for row in rows if row.get("failure_category") == "infra_error")
    failed = total - passed
    agent_failed = failed - infra
    counter = Counter(str(row.get("failure_category") or "unknown") for row in rows if row.get("failure_category") != "passed")
    reasons = Counter(str(row.get("reason") or "") for row in rows if row.get("reason"))
    lines = [
        "# Agent Eval Run Report",
        "",
        "## 总览",
        "",
        f"- total_cases: {total}",
        f"- passed: {passed}",
        f"- failed: {failed}",
        f"- pass_rate: {round(passed / max(1, total), 4)}",
        f"- infra_errors: {infra}",
        f"- agent_failed_cases: {agent_failed}",
        "",
        "## 按类别统计",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category, count in counter.most_common():
        lines.append(f"| {category} | {count} |")
    lines.extend(["", "## 最常见失败原因 Top 5", ""])
    if reasons:
        for reason, count in reasons.most_common(5):
            lines.append(f"- {count}x {_brief(reason)}")
    else:
        lines.append("- 无")
    lines.extend(["", "## 失败 Case 摘要", ""])
    failures = [row for row in rows if row.get("failure_category") != "passed" and not row.get("passed")]
    if not failures:
        lines.append("No failed cases.")
    for row in failures:
        lines.extend(
            [
                f"### {row.get('case_id') or '(unknown)'}",
                "",
                f"- question: {_brief(row.get('question'))}",
                f"- expected_brief: {_brief(row.get('expected_brief'))}",
                f"- actual_brief: {_brief(row.get('actual_brief'))}",
                f"- failure_category: {row.get('failure_category')}",
                f"- reason: {_brief(row.get('reason'))}",
                f"- node_hint: {row.get('node_hint') or ''}",
                f"- trace_path: {row.get('trace_path') or ''}",
                "",
            ]
        )
    lines.extend(["## 本轮运行配置", "", "```json", json.dumps(config or {}, ensure_ascii=False, indent=2, default=str), "```", ""])
    lines.extend(["## 建议下一步", ""])
    for item in _next_steps(counter):
        lines.append(f"- {item}")
    if not counter:
        lines.append("- 无失败类别。")
    return "\n".join(lines)


def write_eval_report(
    classifications: list[FailureClassification | dict[str, Any]],
    *,
    output_dir: str | Path = "outputs/eval_reports",
    config: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> Path:
    stamp = generated_at or datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(output_dir) / f"eval_report_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_eval_report(classifications, config=config), encoding="utf-8")
    return path


def render_run_report(trace: dict[str, Any], *, classification: FailureClassification | dict[str, Any] | None = None) -> str:
    row = _case_dict(classification) if classification is not None else {}
    lines = [
        "# Agent Single Run Report",
        "",
        f"- trace_id: {trace.get('trace_id') or row.get('case_id') or ''}",
        f"- 用户问题: {_brief(trace.get('question'))}",
        "",
        "## Planner tasks",
        "```json",
        json.dumps((trace.get("execution_plan") or {}).get("tasks") or [], ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## TimeResolver facts",
        "```json",
        json.dumps(trace.get("resolved_time_facts") or [], ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## ReAct steps",
        "```json",
        json.dumps(trace.get("react_steps") or [], ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## Tool calls",
        "```json",
        json.dumps(trace.get("tool_calls") or [], ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## RAG queries",
        "```json",
        json.dumps(trace.get("executed_queries") or [], ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## Final status",
        f"- react_status: {trace.get('react_status') or ''}",
        f"- answer: {_brief(trace.get('answer'))}",
        "",
        "## Potential issue classification",
        f"- category: {row.get('failure_category') or 'passed/unknown'}",
        f"- reason: {_brief(row.get('reason'))}",
        f"- node_hint: {row.get('node_hint') or ''}",
    ]
    return "\n".join(lines)


def write_run_report(
    trace: dict[str, Any],
    *,
    output_dir: str | Path = "outputs/run_reports",
    classification: FailureClassification | dict[str, Any] | None = None,
) -> Path:
    trace_id = str(trace.get("trace_id") or "unknown")
    path = Path(output_dir) / f"run_report_{trace_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_run_report(trace, classification=classification), encoding="utf-8")
    return path


__all__ = ["render_eval_report", "write_eval_report", "render_run_report", "write_run_report"]
