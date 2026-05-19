from __future__ import annotations

"""Retrieval ablation runner.

This module compares retrieval strategies under the same question set:
- vector_only: semantic vector retrieval baseline
- hybrid_no_rerank: vector + BM25 + RRF
- hybrid_rerank: hybrid retrieval followed by Qwen rerank

The runner intentionally records both quality and latency. In interviews, this
helps you explain trade-offs instead of only saying "I used hybrid retrieval".
"""

import time
from pathlib import Path
from typing import Any

from mini_rag.config import Settings
from mini_rag.eval import load_eval_questions
from mini_rag.evaluation.metrics import aggregate_rows, citation_hit, extract_retrieved_sources, refusal_hit, source_hit
from mini_rag.rag.chain import RAGQuestionAnswerer
from mini_rag.utils import dump_json, ensure_dir


ABLATION_MODES: tuple[dict[str, Any], ...] = (
    {"name": "vector_only", "retrieval_mode": "vector", "enable_rerank": False},
    {"name": "hybrid_no_rerank", "retrieval_mode": "hybrid", "enable_rerank": False},
    {"name": "hybrid_rerank", "retrieval_mode": "hybrid", "enable_rerank": True},
)


def run_retrieval_ablation(settings: Settings, questions_path: str | Path | None = None) -> dict[str, Any]:
    """Run all retrieval modes and save JSON + Markdown reports."""

    question_file = Path(questions_path) if questions_path else settings.eval_questions_path
    questions = load_eval_questions(question_file)
    qa = RAGQuestionAnswerer(settings)
    mode_reports: list[dict[str, Any]] = []

    for mode in ABLATION_MODES:
        rows: list[dict[str, Any]] = []
        for item in questions:
            question = item["question"]
            expected_sources = list(item.get("expected_sources") or [])
            should_refuse = bool(item.get("should_refuse", False))
            started = time.perf_counter()
            result = qa.ask(
                question,
                retrieval_mode=mode["retrieval_mode"],
                enable_rerank=mode["enable_rerank"],
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            retrieved_sources = extract_retrieved_sources(result)
            answer = str(result.get("answer") or "")
            trace = result.get("trace") or {}
            rows.append(
                {
                    "question": question,
                    "case_id": item.get("id"),
                    "category": item.get("category"),
                    "expected_sources": expected_sources,
                    "retrieved_sources": retrieved_sources,
                    "answer_preview": answer[:500],
                    "route": trace.get("route"),
                    "recall_hit": source_hit(expected_sources, retrieved_sources),
                    "citation_hit": citation_hit(expected_sources, answer),
                    "refusal_hit": refusal_hit(should_refuse, answer, route=trace.get("route"), error=trace.get("error")),
                    "latency_ms": latency_ms,
                    "retrieval_trace": trace.get("retrieval") or trace.get("retrieval_trace"),
                }
            )
        metrics = aggregate_rows(rows)
        mode_reports.append({"mode": mode["name"], "settings": mode, "metrics": metrics.__dict__, "rows": rows})

    report = {
        "question_file": str(question_file),
        "question_count": len(questions),
        "modes": mode_reports,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    ensure_dir(settings.eval_runs_dir)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = settings.eval_runs_dir / f"retrieval_ablation_{stamp}.json"
    md_path = settings.eval_runs_dir / f"retrieval_ablation_{stamp}.md"
    dump_json(json_path, report)
    md_path.write_text(render_ablation_markdown(report), encoding="utf-8")
    report["output_json_path"] = str(json_path)
    report["output_md_path"] = str(md_path)
    return report


def render_ablation_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable ablation report for README/interview use."""

    lines = [
        "# Retrieval Ablation Report",
        "",
        f"- Generated at: {report.get('generated_at')}",
        f"- Question file: `{report.get('question_file')}`",
        f"- Question count: {report.get('question_count')}",
        "",
        "## Summary",
        "",
        "| Mode | Recall@K | Citation Hit Rate | Refusal Hit Rate | Avg Latency(ms) | P95 Latency(ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report.get("modes", []):
        metrics = item.get("metrics", {})
        lines.append(
            "| {mode} | {recall_at_k:.4f} | {citation_hit_rate:.4f} | {refusal_hit_rate:.4f} | {avg_latency_ms:.2f} | {p95_latency_ms:.2f} |".format(
                mode=item.get("mode"),
                recall_at_k=float(metrics.get("recall_at_k") or 0),
                citation_hit_rate=float(metrics.get("citation_hit_rate") or 0),
                refusal_hit_rate=float(metrics.get("refusal_hit_rate") or 0),
                avg_latency_ms=float(metrics.get("avg_latency_ms") or 0),
                p95_latency_ms=float(metrics.get("p95_latency_ms") or 0),
            )
        )
    lines.extend([
        "",
        "## How to explain this in an interview",
        "",
        "- `vector_only` is the semantic retrieval baseline.",
        "- `hybrid_no_rerank` adds BM25 keyword recall and RRF fusion, which helps entity names, product modules and exact policy terms.",
        "- `hybrid_rerank` adds cross-encoder-like semantic ordering with Qwen rerank; it may improve evidence quality but increases latency and depends on external API stability.",
        "",
        "## Per-case Details",
        "",
    ])
    for item in report.get("modes", []):
        lines.extend([f"### {item.get('mode')}", ""])
        for row in item.get("rows", []):
            lines.append(
                "- `{case}` {question} | recall={recall} citation={citation} refusal={refusal} latency={latency}ms | retrieved={retrieved}".format(
                    case=row.get("case_id") or row.get("category") or "case",
                    question=row.get("question"),
                    recall=row.get("recall_hit"),
                    citation=row.get("citation_hit"),
                    refusal=row.get("refusal_hit"),
                    latency=row.get("latency_ms"),
                    retrieved=", ".join(row.get("retrieved_sources") or []),
                )
            )
        lines.append("")
    return "\n".join(lines)
