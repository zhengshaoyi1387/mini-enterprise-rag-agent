from __future__ import annotations

"""Lightweight evaluation runner for the Mini Enterprise RAG Agent.

The eval set is intentionally JSONL and transparent so it can be discussed in an
interview. Every row can specify expected sources and whether the system should
refuse because the knowledge base lacks enough evidence.
"""

import json
import time
from pathlib import Path
from typing import Any

from mini_rag.config import Settings
from mini_rag.evaluation.metrics import aggregate_rows, citation_hit, extract_retrieved_sources, refusal_hit, source_hit
from mini_rag.rag.chain import RAGQuestionAnswerer
from mini_rag.utils import dump_json, ensure_dir


def load_eval_questions(path: str | Path) -> list[dict[str, Any]]:
    """Read jsonl evaluation cases.

    Example line:
    ``{"question": "...", "expected_sources": ["a.md"], "should_refuse": false}``
    """

    path = Path(path)
    questions: list[dict[str, Any]] = []
    if not path.exists():
        return questions
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        item.setdefault("id", f"case_{line_number:03d}")
        questions.append(item)
    return questions


def run_eval(settings: Settings, questions_path: str | Path | None = None) -> dict[str, Any]:
    """Run a practical RAG quality eval and save JSON + Markdown reports.

    Metrics:
    - recall_at_k: expected source appears in retrieved sources.
    - citation_hit_rate: answer text includes expected source names.
    - refusal_hit_rate: no-answer/unsafe cases are refused.
    - latency: average and p95 latency for local performance discussion.
    """

    question_file = Path(questions_path) if questions_path else settings.eval_questions_path
    questions = load_eval_questions(question_file)
    qa = RAGQuestionAnswerer(settings)
    rows: list[dict[str, Any]] = []

    for item in questions:
        question = item["question"]
        expected_sources = list(item.get("expected_sources") or [])
        should_refuse = bool(item.get("should_refuse", False))
        start = time.perf_counter()
        result = qa.ask(question)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        retrieved_sources = extract_retrieved_sources(result)
        answer = str(result.get("answer") or "")
        trace = result.get("trace") or {}
        rows.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "question": question,
                "answer": answer,
                "expected_sources": expected_sources,
                "retrieved_sources": retrieved_sources,
                "recall_hit": source_hit(expected_sources, retrieved_sources),
                "citation_hit": citation_hit(expected_sources, answer),
                "refusal_hit": refusal_hit(should_refuse, answer, route=trace.get("route"), error=trace.get("error")),
                "latency_ms": latency_ms,
                "trace": trace,
            }
        )

    metrics = aggregate_rows(rows)
    report: dict[str, Any] = {
        "question_file": str(question_file),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **metrics.__dict__,
        "rows": rows,
    }
    ensure_dir(settings.eval_runs_dir)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = settings.eval_runs_dir / f"eval_{stamp}.json"
    md_path = settings.eval_runs_dir / f"eval_{stamp}.md"
    dump_json(json_path, report)
    md_path.write_text(render_eval_markdown(report), encoding="utf-8")
    report["output_path"] = str(json_path)
    report["output_md_path"] = str(md_path)
    return report


def render_eval_markdown(report: dict[str, Any]) -> str:
    """Render a readable eval report for interview/demo documentation."""

    lines = [
        "# RAG Eval Report",
        "",
        f"- Generated at: {report.get('generated_at')}",
        f"- Question file: `{report.get('question_file')}`",
        f"- Question count: {report.get('question_count')}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| recall_at_k | {float(report.get('recall_at_k') or 0):.4f} |",
        f"| citation_hit_rate | {float(report.get('citation_hit_rate') or 0):.4f} |",
        f"| refusal_hit_rate | {float(report.get('refusal_hit_rate') or 0):.4f} |",
        f"| avg_latency_ms | {float(report.get('avg_latency_ms') or 0):.2f} |",
        f"| p95_latency_ms | {float(report.get('p95_latency_ms') or 0):.2f} |",
        "",
        "## Cases",
        "",
    ]
    for row in report.get("rows", []):
        lines.extend(
            [
                f"### {row.get('id')} / {row.get('category') or 'uncategorized'}",
                "",
                f"- Question: {row.get('question')}",
                f"- Expected sources: {', '.join(row.get('expected_sources') or []) or '(none)'}",
                f"- Retrieved sources: {', '.join(row.get('retrieved_sources') or []) or '(none)'}",
                f"- recall_hit: {row.get('recall_hit')}",
                f"- citation_hit: {row.get('citation_hit')}",
                f"- refusal_hit: {row.get('refusal_hit')}",
                f"- latency_ms: {row.get('latency_ms')}",
                "",
            ]
        )
    return "\n".join(lines)
