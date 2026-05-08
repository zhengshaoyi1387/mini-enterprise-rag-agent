from __future__ import annotations

"""Small, dependency-light evaluation metrics for the demo project.

The goal is not to pretend this is a full academic benchmark. These functions
provide transparent metrics that are easy to explain in an interview and easy to
extend later: source recall, citation hit rate, refusal behavior and latency.
"""

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable


@dataclass(frozen=True)
class EvalMetrics:
    """Aggregated metrics returned by eval and ablation scripts."""

    question_count: int
    recall_at_k: float
    citation_hit_rate: float
    refusal_hit_rate: float
    avg_latency_ms: float
    p95_latency_ms: float


def _normalize_source(value: str | None) -> str:
    """Normalize source names for robust comparison.

    Many traces contain paths such as ``data/raw/foo.md`` while evaluation data
    usually stores just ``foo.md``. Comparing by suffix avoids false negatives
    without hiding genuinely wrong sources.
    """

    return (value or "").replace("\\", "/").split("/")[-1].strip()


def source_hit(expected_sources: Iterable[str], retrieved_sources: Iterable[str]) -> bool:
    """Whether at least one expected source appears in retrieved sources.

    Empty ``expected_sources`` means the case is not testing retrieval recall,
    so it is considered a pass for this metric.
    """

    expected = {_normalize_source(item) for item in expected_sources if item}
    if not expected:
        return True
    retrieved = {_normalize_source(item) for item in retrieved_sources if item}
    return bool(expected & retrieved)


def citation_hit(expected_sources: Iterable[str], answer: str) -> bool:
    """Whether all expected sources are mentioned in the answer text.

    This simple metric is intentionally explainable. For a production benchmark,
    you could replace it with structured citation parsing or LLM-as-judge.
    """

    expected = [_normalize_source(item) for item in expected_sources if item]
    if not expected:
        return True
    return all(source and source in (answer or "") for source in expected)


def refusal_hit(should_refuse: bool, answer: str, route: str | None = None, error: str | None = None) -> bool:
    """Whether the system correctly refused a no-answer or unsafe case."""

    if not should_refuse:
        return True
    text = f"{answer or ''}\n{error or ''}".lower()
    refusal_markers = (
        "证据不足",
        "无法回答",
        "不能回答",
        "不能执行",
        "已被安全策略拒绝",
        "拒绝",
        "not enough evidence",
        "cannot answer",
    )
    return route == "reject" or any(marker.lower() in text for marker in refusal_markers)


def percentile_95(values: list[float]) -> float:
    """Return a deterministic nearest-rank p95 for small local eval sets."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return float(ordered[index])


def aggregate_rows(rows: list[dict[str, Any]]) -> EvalMetrics:
    """Aggregate per-question rows into explainable metrics."""

    total = max(1, len(rows))
    latencies = [float(row.get("latency_ms") or 0.0) for row in rows]
    return EvalMetrics(
        question_count=len(rows),
        recall_at_k=round(sum(bool(row.get("recall_hit")) for row in rows) / total, 4),
        citation_hit_rate=round(sum(bool(row.get("citation_hit")) for row in rows) / total, 4),
        refusal_hit_rate=round(sum(bool(row.get("refusal_hit")) for row in rows) / total, 4),
        avg_latency_ms=round(mean(latencies), 2) if latencies else 0.0,
        p95_latency_ms=round(percentile_95(latencies), 2),
    )


def extract_retrieved_sources(result: dict[str, Any]) -> list[str]:
    """Extract source names from a RAG/Agent result regardless of response shape."""

    sources = result.get("sources") or []
    names: list[str] = []
    for source in sources:
        if isinstance(source, dict):
            value = source.get("source") or source.get("file_name") or source.get("filename")
            if value:
                names.append(str(value))
    return names
